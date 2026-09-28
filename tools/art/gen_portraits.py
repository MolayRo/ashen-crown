# -*- coding: utf-8 -*-
"""
《灰烬王冠》角色头像生成器（GBA《火焰纹章》风格半身像）

输出
  assets/portraits.png   精灵表
  assets/portraits.json  {"frames": {帧名: [x, y, w, h, 0, 0]}}
预览
  tools/art/preview/portraits/

画法（全部 1 倍像素、无抗锯齿）
  矢量形状（样条轮廓 / 带宽度的发束）→ 像素中心采样光栅化
  → 分部位按色阶着色（光源左上：边缘偏移法 + 投影 + 发束 UV 高光）
  → 描边（外轮廓 INK，部件交界用前方部件材质的最暗色）
  → 贴五官（眼 / 眉 / 口 模板随表情与帧切换；同一表情三帧只有眼、口不同）

帧名（80×80，锚点 0,0 即左上角）
  {id}_{expr}        闭嘴睁眼
  {id}_{expr}_talk   张嘴（说话口型）
  {id}_{expr}_blink  闭眼（眨眼）
  {id}_mini          32×32 脸部特写：同一套矢量形状按 0.68 倍重绘 + 专用小五官（不是裁切缩放）
表情：可操控 8 人 + valder/aldric 为 normal smile angry sad surprise；
      gord hagen morgan grimm martha oswin abbot 为 normal smile angry（反派 smile 为冷笑）；
      soldier villager 只有 normal。
朝向：人物面朝画面右方；显示在右侧时由程序水平镜像。

用法
  python tools/art/gen_portraits.py            生成精灵表 + 自检 + 预览
  python tools/art/gen_portraits.py --preview NAME --only elwin,nora [--exprs ..] [--scale 4]
                                                只出放大预览（调形状时用）
改人物：各 build_xxx() 里的形状（基准 80×80 坐标）与 CHARS 表里的五官类型/锚点/皱纹。
"""
import os
import sys
import math
import argparse

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from palette import PAL, INK, INK2, hx  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
OUT_PNG = os.path.join(ROOT, 'assets', 'portraits.png')
OUT_JSON = os.path.join(ROOT, 'assets', 'portraits.json')
PREV = os.path.join(HERE, 'preview', 'portraits')

S = 80        # 头像边长
MINI = 32     # 小头像边长

# ---------------------------------------------------------------- 颜色
EXTRA = {
    # 摩根：病态苍白皮肤（描边色, 深阴影, 阴影, 基色, 高光）
    'skin_pale': ['#3a2632', '#6e5662', '#a48e98', '#d0c2c4', '#eee6e2'],
}
EXTRA_PAL = {k: [hx(c) for c in v] for k, v in EXTRA.items()}


def ramp(name):
    return PAL[name] if name in PAL else EXTRA_PAL[name]


# ---------------------------------------------------------------- 几何
def _cr_seg(p0, p1, p2, p3, n):
    """向心 Catmull-Rom：p1→p2 段，n 个采样（不含 p2）。"""
    def tj(t, a, b):
        return t + max(math.hypot(b[0] - a[0], b[1] - a[1]), 1e-4) ** 0.5
    t0 = 0.0
    t1 = tj(t0, p0, p1)
    t2 = tj(t1, p1, p2)
    t3 = tj(t2, p2, p3)

    def lerp(a, b, ta, tb, t):
        if tb - ta < 1e-9:
            return a
        wa, wb = (tb - t) / (tb - ta), (t - ta) / (tb - ta)
        return (wa * a[0] + wb * b[0], wa * a[1] + wb * b[1])
    out = []
    for k in range(n):
        t = t1 + (t2 - t1) * k / n
        a1 = lerp(p0, p1, t0, t1, t)
        a2 = lerp(p1, p2, t1, t2, t)
        a3 = lerp(p2, p3, t2, t3, t)
        b1 = lerp(a1, a2, t0, t2, t)
        b2 = lerp(a2, a3, t1, t3, t)
        out.append(lerp(b1, b2, t1, t2, t))
    return out


def spline(pts, closed=False, n=10):
    P = [(float(p[0]), float(p[1])) for p in pts]
    if len(P) == 2 and not closed:
        return [P[0], P[1]]
    if closed:
        ext = [P[-1]] + P + [P[0], P[1]]
    else:
        ext = ([(2 * P[0][0] - P[1][0], 2 * P[0][1] - P[1][1])] + P +
               [(2 * P[-1][0] - P[-2][0], 2 * P[-1][1] - P[-2][1])])
    out = []
    for i in range(1, len(ext) - 2):
        out += _cr_seg(ext[i - 1], ext[i], ext[i + 1], ext[i + 2], n)
    if not closed:
        out.append(P[-1])
    return out


def shape(pts, n=10):
    """闭合轮廓：(x,y) 平滑经过；(x,y,1) 为尖角。"""
    sharp = [len(p) > 2 and bool(p[2]) for p in pts]
    P = [(float(p[0]), float(p[1])) for p in pts]
    if not any(sharp):
        return spline(P, closed=True, n=n)
    k = sharp.index(True)
    P = P[k:] + P[:k]
    sharp = sharp[k:] + sharp[:k]
    P.append(P[0])
    sharp.append(True)
    out = []
    start = 0
    for i in range(1, len(P)):
        if sharp[i]:
            seg = P[start:i + 1]
            if len(seg) == 2:
                out.append(seg[0])
            else:
                out += spline(seg, closed=False, n=n)[:-1]
            start = i
    return out


def raster(poly, w, h):
    """多边形 → 布尔掩码（像素中心采样，奇偶规则，无抗锯齿）。"""
    m = np.zeros((h, w), bool)
    if len(poly) < 3:
        return m
    a = np.asarray(poly, float)
    x0, y0 = a[:, 0], a[:, 1]
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    ylo = max(0, int(math.floor(y0.min())) - 1)
    yhi = min(h - 1, int(math.ceil(y0.max())) + 1)
    for py in range(ylo, yhi + 1):
        yc = py + 0.5
        c = ((y0 <= yc) & (y1 > yc)) | ((y1 <= yc) & (y0 > yc))
        if not c.any():
            continue
        xi = x0[c] + (yc - y0[c]) * (x1[c] - x0[c]) / (y1[c] - y0[c])
        xi.sort()
        for xa, xb in zip(xi[0::2], xi[1::2]):
            ia = max(0, int(math.ceil(xa - 0.5)))
            ib = min(w, int(math.ceil(xb - 0.5)))
            if ib > ia:
                m[py, ia:ib] = True
    return m


class Strand:
    """带宽度的发束/布条：中心线过控制点（样条），宽度沿线插值，末端宽 0 即尖梢。
    记录中心线采样，供像素求 (u 沿线 0→1, v 横向 -1→1) 做着色。"""

    def __init__(self, pts, widths, n=48):
        assert len(pts) == len(widths)
        dense = spline(pts, closed=False, n=14)
        if len(pts) == 2:
            dense = [(pts[0][0] + (pts[1][0] - pts[0][0]) * t / 20.0,
                      pts[0][1] + (pts[1][1] - pts[0][1]) * t / 20.0) for t in range(21)]
        d = np.asarray(dense, float)
        seg = np.hypot(np.diff(d[:, 0]), np.diff(d[:, 1]))
        L = np.concatenate([[0.0], np.cumsum(seg)])
        tot = max(L[-1], 1e-6)
        uc = []
        for p in pts:
            j = int(np.argmin((d[:, 0] - p[0]) ** 2 + (d[:, 1] - p[1]) ** 2))
            uc.append(L[j] / tot)
        uc[0], uc[-1] = 0.0, 1.0
        uc = np.maximum.accumulate(np.array(uc))
        s = np.linspace(0, tot, n)
        self.C = np.stack([np.interp(s, L, d[:, 0]), np.interp(s, L, d[:, 1])], 1)
        self.u = s / tot
        self.w = np.interp(self.u, uc, np.asarray(widths, float))
        T = np.gradient(self.C, axis=0)
        T /= np.maximum(np.hypot(T[:, 0], T[:, 1]), 1e-9)[:, None]
        self.T = T
        self.N = np.stack([-T[:, 1], T[:, 0]], 1)

    def xf(self, s, ox, oy):
        o = Strand.__new__(Strand)
        o.C = self.C * s + np.array([ox, oy])
        o.u, o.w, o.T, o.N = self.u, self.w * s, self.T, self.N
        return o

    @property
    def poly(self):
        hw = (self.w / 2)[:, None]
        left = self.C + self.N * hw
        right = self.C - self.N * hw
        return [tuple(p) for p in left] + [tuple(p) for p in right[::-1]]

    def uv(self, mask):
        ys, xs = np.nonzero(mask)
        if len(ys) == 0:
            return ys, xs, np.zeros(0), np.zeros(0), np.zeros((0, 2))
        P = np.stack([xs + 0.5, ys + 0.5], 1)
        d2 = ((P[:, None, :] - self.C[None, :, :]) ** 2).sum(-1)
        j = d2.argmin(1)
        off = P - self.C[j]
        v = (off * self.N[j]).sum(1) / np.maximum(self.w[j] / 2, 0.7)
        return ys, xs, self.u[j], np.clip(v, -1.5, 1.5), self.N[j]


# ---------------------------------------------------------------- 掩码运算
def shift(m, dx, dy):
    """把掩码内容平移 (dx, dy)：out[y, x] = m[y-dy, x-dx]。"""
    H, W = m.shape
    out = np.zeros_like(m)
    if abs(dx) >= W or abs(dy) >= H:
        return out
    ys_d = slice(max(dy, 0), H + min(dy, 0))
    ys_s = slice(max(-dy, 0), H + min(-dy, 0))
    xs_d = slice(max(dx, 0), W + min(dx, 0))
    xs_s = slice(max(-dx, 0), W + min(-dx, 0))
    out[ys_d, xs_d] = m[ys_s, xs_s]
    return out


def near_edge(m, dx, dy, k=1):
    """m 内、沿 (dx,dy) 方向 k 步内会走出 m 的像素。"""
    acc = np.ones_like(m)
    for j in range(1, k + 1):
        acc &= shift(m, -int(round(dx * j)), -int(round(dy * j)))
    return m & ~acc



def erode(m, n=1):
    for _ in range(n):
        m = m & shift(m, 1, 0) & shift(m, -1, 0) & shift(m, 0, 1) & shift(m, 0, -1)
    return m



def line_px(pts):
    """折线 → 像素（8 连通、去 L 形拐角的干净 1px 线）。坐标：像素 (i,j) 覆盖 [i,i+1)。"""
    dense = []
    for a, b in zip(pts[:-1], pts[1:]):
        n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1])) * 4) + 1
        for i in range(n):
            t = i / n
            dense.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    dense.append(pts[-1])
    px = []
    for x, y in dense:
        q = (int(math.floor(x)), int(math.floor(y)))
        if not px or px[-1] != q:
            px.append(q)
    out = []
    for i, q in enumerate(px):
        if out and i < len(px) - 1:
            a, c = out[-1], px[i + 1]
            if abs(a[0] - c[0]) == 1 and abs(a[1] - c[1]) == 1:
                continue
        out.append(q)
    return out


def speckle(x, y, n, seed=0):
    """无规律的稀疏点：返回 True 的概率约 1/n（避免取模造成的斜格纹）。"""
    h = (int(x) * 73856093) ^ (int(y) * 19349663) ^ (seed * 83492791)
    h = (h ^ (h >> 13)) * 1274126177
    return ((h >> 7) & 0xffff) % n == 0


# ---------------------------------------------------------------- 场景
LIGHT = np.array([-0.55, -0.835])   # 指向光源（左上）


class Part:
    def __init__(self, name, mask, rmp, shader, line, line_same, group, line_ok, outer):
        self.name = name
        self.mask = mask
        self.ramp = rmp
        self.shader = shader
        self.line = line
        self.line_same = line_same
        self.group = group or name
        self.line_ok = line_ok
        self.same_ok = None      # 同组交界线允许出现的像素（发束根部不画分隔线）
        self.same_dirs = 'udlr'  # 同组交界线只在这些方向的邻居处画（发束只画下/右＝背光侧）
        self.outer = outer
        self.strand = None
        self.idx = None
        self.paint = []      # 着色后的附加绘制 fn(scene, part, idx)
        self.over = []       # 直接颜色覆盖 [(mask, rgba)]


class Scene:
    def __init__(self, w=S, h=S, scale=1.0, ox=0.0, oy=0.0):
        self.w, self.h = w, h
        self.s, self.ox, self.oy = scale, ox, oy
        self.parts = []
        self.byname = {}
        self.overlays = []   # 固定像素贴花 (x, y, rows, cmap)：纹章、吊坠等（基准坐标）

    # ---- 几何 → 掩码（带缩放平移，供小头像复用同一套形状）
    def P(self, pts):
        return [(x * self.s + self.ox, y * self.s + self.oy) for x, y in pts]

    def poly(self, pts):
        return raster(self.P(pts), self.w, self.h)

    def shp(self, pts, n=10):
        return raster(self.P(shape(pts, n)), self.w, self.h)

    def ell(self, cx, cy, rx, ry, n=48):
        pts = [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n))
               for i in range(n)]
        return self.poly(pts)

    def st(self, strand):
        s2 = strand.xf(self.s, self.ox, self.oy)
        return s2, raster(s2.poly, self.w, self.h)

    def X(self, x, y):
        return (x * self.s + self.ox, y * self.s + self.oy)

    # ---- 部件
    def add(self, name, mask, rmp, shader=None, line=0, line_same='same', group=None,
            line_ok=None, outer=INK, clip=None, cut=None):
        if clip is not None:
            mask = mask & clip
        if cut is not None:
            mask = mask & ~cut
        if line_same == 'same':
            line_same = line
        p = Part(name, mask, ramp(rmp) if isinstance(rmp, str) else rmp, shader,
                 line, line_same, group, line_ok, outer)
        self.parts.append(p)
        self.byname[name] = p
        return p

    def add_strand(self, name, strand, rmp, shader, **kw):
        s2, m = self.st(strand)
        clipm = kw.pop('clip', None)
        if clipm is not None:
            m = m & clipm
        p = self.add(name, m, rmp, shader, **kw)
        p.strand = s2
        return p

    def mask_of(self, names=None, groups=None, after=None, before=None):
        m = np.zeros((self.h, self.w), bool)
        ia = self.parts.index(after) if after is not None else -1
        ib = self.parts.index(before) if before is not None else len(self.parts)
        for i, p in enumerate(self.parts):
            if i <= ia or i >= ib:
                continue
            if (names and p.name in names) or (groups and p.group in groups):
                m |= p.mask
        return m

    def visible(self, part):
        """part 未被其后部件遮挡的像素。"""
        i = self.parts.index(part)
        m = part.mask.copy()
        for q in self.parts[i + 1:]:
            m &= ~q.mask
        return m

    def color(self, p, c):
        if c is None:
            return None
        if isinstance(c, (int, np.integer)):
            return p.ramp[max(0, min(len(p.ramp) - 1, int(c)))]
        return c

    def render(self):
        H, W = self.h, self.w
        owner = np.full((H, W), -1, int)
        for i, p in enumerate(self.parts):
            owner[p.mask] = i
        rgba = np.zeros((H, W, 4), np.uint8)
        for i, p in enumerate(self.parts):
            sel = owner == i
            if not sel.any():
                p.idx = np.full((H, W), 3, int)
                continue
            idx = p.shader(self, p) if p.shader else np.full((H, W), 3, int)
            for fn in p.paint:
                fn(self, p, idx)
            p.idx = idx
            cols = np.array(p.ramp, np.uint8)
            rgba[sel] = cols[np.clip(idx[sel], 0, len(cols) - 1)]
            for m, c in p.over:
                rgba[sel & m] = c
        # ---- 描边
        pad = np.pad(owner, 1, mode='edge')
        pad[0, :] = -1
        nbs = [pad[0:H, 1:W + 1], pad[2:H + 2, 1:W + 1], pad[1:H + 1, 0:W], pad[1:H + 1, 2:W + 2]]
        groups = {}
        gid = np.array([groups.setdefault(p.group, len(groups)) for p in self.parts] + [-2])
        for i, p in enumerate(self.parts):
            sel = owner == i
            if not sel.any():
                continue
            outer = np.zeros((H, W), bool)
            diff = np.zeros((H, W), bool)
            same = np.zeros((H, W), bool)
            for d, nb in zip('udlr', nbs):
                outer |= sel & (nb == -1)
                behind = sel & (nb >= 0) & (nb < i)
                sg = behind & (gid[np.where(nb >= 0, nb, -1)] == gid[i])
                if d in p.same_dirs:
                    same |= sg
                diff |= behind & ~sg
            ok = p.line_ok if p.line_ok is not None else np.ones((H, W), bool)
            c = self.color(p, p.line)
            if c is not None:
                rgba[diff & ~outer & ok] = c
            c = self.color(p, p.line_same)
            if c is not None:
                oks = p.same_ok if p.same_ok is not None else ok
                rgba[same & ~diff & ~outer & oks] = c
            if p.outer is not None:
                rgba[outer] = self.color(p, p.outer)
        for x, y, rows, cmap in self.overlays:
            px, py = self.X(x, y)
            for r, row in enumerate(rows):
                for c, ch in enumerate(row):
                    col = cmap.get(ch)
                    xx, yy = int(round(px)) + c, int(round(py)) + r
                    if col is not None and 0 <= xx < W and 0 <= yy < H and owner[yy, xx] >= 0:
                        rgba[yy, xx] = col
        self.owner = owner
        self.rgba = rgba
        return rgba

    def ids(self, *names):
        return {self.parts.index(self.byname[n]) for n in names if n in self.byname}


# ---------------------------------------------------------------- 着色器
def sh_rim(base=3, dark=((1, 1, 2, 1),), light=((-1, -1, 1, 1),), extra=None, lo=1, hi=4):
    """边缘偏移法：朝 (dx,dy) 方向 k 像素内出界 → 加 delta。dark 为右下背光，light 为左上受光。"""
    def f(sc, p):
        m = p.mask
        idx = np.full(m.shape, base, int)
        for dx, dy, k, dl in dark:
            idx[near_edge(m, dx, dy, k)] -= dl
        for dx, dy, k, dl in light:
            idx[near_edge(m, dx, dy, k)] += dl
        idx = np.clip(idx, lo, hi)
        if extra:
            extra(sc, p, idx)
        return idx
    return f


def sh_flat(i):
    def f(sc, p):
        return np.full(p.mask.shape, i, int)
    return f


# ---------------------------------------------------------------- 头发光照
L3 = np.array([-0.5, -0.72, 0.48])
L3 = L3 / np.linalg.norm(L3)


class HairLight:
    """整头头发共用：球面光照分档（亮/中/暗）+ 高光带。坐标一律用 80×80 基准空间。"""

    def __init__(self, cx, cy, r, band=None, base=3, lo=1, hi=4, t1=0.40, t2=0.02):
        self.cx, self.cy, self.r = cx, cy, r
        self.band, self.base, self.lo, self.hi, self.t1, self.t2 = band, base, lo, hi, t1, t2

    def level(self, xs, ys, sc):
        bx = ((xs + 0.5) - sc.ox) / sc.s
        by = ((ys + 0.5) - sc.oy) / sc.s
        nx = (bx - self.cx) / self.r
        ny = (by - self.cy) / self.r
        d = np.hypot(nx, ny)
        k = np.where(d > 0.98, 0.98 / np.maximum(d, 1e-6), 1.0)
        nx, ny = nx * k, ny * k
        nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
        lit = nx * L3[0] + ny * L3[1] + nz * L3[2]
        lv = np.where(lit > self.t1, self.base, np.where(lit > self.t2, self.base - 1, self.base - 2))
        return lv, bx, by


def arc_band(cx, cy, r0, r1, a0, a1, teeth=0.0, tw=8.0, phase=0.0, strand_teeth=2.5):
    """高光带：圆心 (cx,cy)、半径 r0..r1、角度 a0..a1（度；y 向下，-90=正上）。
    teeth>0：整块发团的内沿锯齿；发束则按横向坐标 v 向内延伸（每束一个尖牙，顺着发束）。"""
    def f(bx, by, v=None):
        dx, dy = bx - cx, by - cy
        r = np.hypot(dx, dy)
        a = np.degrees(np.arctan2(dy, dx))
        inner = np.full(r.shape, float(r0))
        if v is not None:
            inner = r0 - strand_teeth * np.clip(1 - np.abs(v) * 1.25, 0, 1)
        elif teeth:
            saw = ((a - a0 + phase) / tw) % 1.0
            inner = r0 - teeth * (1 - np.abs(saw * 2 - 1))
        outer = r1 - 0.8 * np.clip(np.abs(v) if v is not None else 0, 0, 1)
        return (r >= inner) & (r <= outer) & (a >= a0) & (a <= a1)
    return f


def hair_strand_shader(hl, dark_side=0.35, tip=None, band_v=0.8):
    def f(sc, p):
        m = p.mask
        idx = np.full(m.shape, hl.base, int)
        ys, xs, u, v, N = p.strand.uv(m)
        if len(ys):
            lv, bx, by = hl.level(xs, ys, sc)
            facing = v * (N @ LIGHT)
            val = lv.copy()
            val[facing < -dark_side] -= 1
            if tip is not None:
                val[u > tip] -= 1
            if hl.band is not None:
                b = hl.band(bx, by, v) & (facing > -0.3) & (np.abs(v) < band_v)
                val[b] = hl.hi
            idx[ys, xs] = val
        front = sc.mask_of(groups=(p.group,), after=p)
        sh = m & shift(front, 1, 1) & ~front
        idx[sh] -= 1
        return np.clip(idx, hl.lo, hl.hi)
    return f


def hair_mass_shader(hl, rim=2):
    def f(sc, p):
        m = p.mask
        idx = np.full(m.shape, hl.base, int)
        ys, xs = np.nonzero(m)
        if len(ys):
            lv, bx, by = hl.level(xs, ys, sc)
            val = lv.copy()
            if hl.band is not None:
                val[hl.band(bx, by)] = hl.hi
            idx[ys, xs] = val
        idx[near_edge(m, 1, 1, rim)] -= 1
        front = sc.mask_of(groups=(p.group,), after=p)
        idx[m & shift(front, 1, 1) & ~front] -= 1
        return np.clip(idx, hl.lo, hl.hi)
    return f


# ---------------------------------------------------------------- 五官模板
# 符号：K=INK 线  0-3=虹膜色阶(暗→亮)  W=眼白  w=眼白阴影  H=高光
#       l=皮肤描边色  S=皮肤深影  s=皮肤阴影  h=皮肤高光  n=皮肤基色
#       b=眉色  B=眉深色  D=口腔深  d=口腔  t=舌  T=牙  .=不画
# 模板值可为行列表，或 (行列表, dx, dy) 表示相对锚点再偏移。
EYE_M = {
    'near': {
        'normal': [
            "...KKKKK.",
            ".KKK0000K",
            "K.W0H001.",
            "..W00112.",
            "..lW1233.",
            "....lll..",
        ],
        'smile': [
            "...KKKKK.",
            ".KKK0000K",
            "K.W0H001.",
            "..lW0112l",
            "....llll.",
        ],
        'angry': [
            ".KKK.....",
            "KKKKKKK..",
            "K.W0KKKKK",
            "..W0H01K.",
            "..lW1233.",
            "....lll..",
        ],
        'sad': [
            "......KK.",
            "...KKK00K",
            "KKKW0H01.",
            "..W00112.",
            "..lW1233.",
            "....lll..",
        ],
        'surprise': ([
            "...KKKKK.",
            ".KKKwwwwK",
            "K.W1000W.",
            "..W0H02W.",
            "..lW123W.",
            "....lll..",
        ], 0, -1),
        'blink': [
            ".........",
            ".........",
            "K......K.",
            ".KKKKKK..",
            "...ll....",
        ],
        'blink_smile': [
            ".........",
            "...KKK...",
            "..K...K..",
            ".K.....K.",
        ],
        'blink_angry': [
            ".........",
            "KK.......",
            "..KKK....",
            ".....KKKK",
        ],
        'blink_sad': [
            ".........",
            ".........",
            ".....KKK.",
            "KKKKK....",
        ],
    },
    'far': {
        'normal': [
            ".KKKK..",
            "K0000KK",
            "WH001.K",
            "W0112..",
            ".1233..",
            "..ll...",
        ],
        'smile': [
            ".KKKK..",
            "K0000KK",
            "WH001.K",
            "l0112l.",
            ".llll..",
        ],
        'angry': [
            "....KK.",
            "..KKKKK",
            "KKK001K",
            "W0H12..",
            ".1233..",
            "..ll...",
        ],
        'sad': [
            "KK.....",
            "K0KKK..",
            "WH00KKK",
            "W0112.K",
            ".1233..",
            "..ll...",
        ],
        'surprise': ([
            ".KKKK..",
            "KwwwwKK",
            "W1000WK",
            "W0H02W.",
            ".W123..",
            "..ll...",
        ], 0, -1),
        'blink': [
            ".......",
            ".......",
            "K.....K",
            ".KKKKK.",
            "..ll...",
        ],
        'blink_smile': [
            ".......",
            "..KKK..",
            ".K...K.",
            "K.....K",
        ],
        'blink_angry': [
            ".......",
            ".....KK",
            "..KKK..",
            "KK.....",
        ],
        'blink_sad': [
            ".......",
            ".......",
            "KKK....",
            "...KKKK",
        ],
    },
}

BROW_M = {
    'near': {
        'normal': [
            "...BBBBB.",
            ".BBB...BB",
            "B........",
        ],
        'smile': ([
            "..BBBBB..",
            ".B.....BB",
            "B........",
        ], 0, -1),
        'angry': [
            "BB.......",
            "..BBB....",
            ".....BBB.",
            ".......BB",
        ],
        'sad': [
            "......BB.",
            "....BB..B",
            "BBBB.....",
        ],
        'surprise': ([
            "..BBBBB..",
            ".B.....BB",
            "B........",
        ], 0, -2),
    },
    'far': {
        'normal': [
            "BBBBB..",
            "B....BB",
        ],
        'smile': ([
            ".BBBB..",
            "B....B.",
        ], 0, -1),
        'angry': [
            ".....BB",
            "..BBB..",
            "BB.....",
            "B......",
        ],
        'sad': [
            "BB.....",
            "..BBB..",
            ".....BB",
        ],
        'surprise': ([
            ".BBBB..",
            "B....B.",
        ], 0, -2),
    },
}

MOUTH_M = {
    'normal': [
        ".llll",
        "..ss.",
    ],
    'normal_talk': [
        ".llll",
        ".lDDl",
        "..ll.",
    ],
    'smile': [
        "l...l",
        ".lll.",
    ],
    'smile_talk': [
        "lllll",
        ".lDdl",
        "..ll.",
    ],
    'angry': [
        ".lll.",
        "l...l",
    ],
    'angry_talk': [
        ".llll.",
        "lTTTTl",
        "lDDDDl",
        ".llll.",
    ],
    'sad': [
        "..ll.",
        ".l..l",
    ],
    'sad_talk': [
        "..ll.",
        ".lDDl",
        ".llll",
    ],
    'surprise': [
        "..ll.",
        "..ss.",
    ],
    'surprise_talk': [
        "..ll.",
        ".lDDl",
        ".lDDl",
        "..ll.",
    ],
}

EYE_F = {
    'near': {
        'normal': ([
            "...KKKKK..",
            ".KKK0000K.",
            "KK.W0H001.",
            "K.W00H012.",
            "..W001123.",
            "..KW01233.",
            "....lll...",
        ], 0, -1),
        'smile': ([
            "...KKKKK..",
            ".KKK0000K.",
            "KK.W0H001.",
            "K.W00H012.",
            "..lW0112l.",
            "....llll..",
        ], 0, -1),
        'angry': ([
            "..KK......",
            ".KKKKKK...",
            "KK.W0KKKK.",
            "K.W00H0KK.",
            "..W001123.",
            "..KW01233.",
            "....lll...",
        ], 0, -1),
        'sad': ([
            "......KK..",
            "...KKK00K.",
            "KKKKW0H01.",
            "K.W00H012.",
            "..W001123.",
            "..KW01233.",
            "....lll...",
        ], 0, -1),
        'surprise': ([
            "...KKKKK..",
            ".KKKwwwwK.",
            "KK.W1000W.",
            "K.W00H01W.",
            "..W00H12W.",
            "..W01123W.",
            "..KWW33W..",
            "....lll...",
        ], 0, -2),
        'blink': ([
            "..........",
            "..........",
            "..........",
            "KK......K.",
            ".KKKKKKK..",
            "..K.lll...",
        ], 0, -1),
        'blink_smile': ([
            "..........",
            "..........",
            "...KKKK...",
            "..K....K..",
            ".K......K.",
        ], 0, -1),
        'blink_angry': ([
            "..........",
            "KK........",
            "..KKK.....",
            ".....KKKK.",
            "..........",
        ], 0, -1),
        'blink_sad': ([
            "..........",
            "..........",
            "..........",
            "......KK..",
            "KKKKKK....",
        ], 0, -1),
    },
    'far': {
        'normal': ([
            "..KKKK..",
            ".K0000KK",
            "KWH001.K",
            ".W0H12..",
            ".W0123..",
            ".W1233K.",
            "..lll...",
        ], 0, -1),
        'smile': ([
            "..KKKK..",
            ".K0000KK",
            "KWH001.K",
            ".W0H12..",
            ".l0123l.",
            "..llll..",
        ], 0, -1),
        'angry': ([
            ".....KK.",
            "...KKKKK",
            "KKKK01.K",
            ".W0H12..",
            ".W0123..",
            ".W1233K.",
            "..lll...",
        ], 0, -1),
        'sad': ([
            ".KK.....",
            ".K0KKK..",
            "KWH00KKK",
            ".W0H12.K",
            ".W0123..",
            ".W1233K.",
            "..lll...",
        ], 0, -1),
        'surprise': ([
            "..KKKK..",
            ".KwwwwKK",
            "KW1000WK",
            ".W0H01W.",
            ".W0H12W.",
            ".W0123W.",
            ".WW33WK.",
            "..lll...",
        ], 0, -2),
        'blink': ([
            "........",
            "........",
            "........",
            "K.....KK",
            ".KKKKK..",
            "..lll.K.",
        ], 0, -1),
        'blink_smile': ([
            "........",
            "........",
            "..KKK...",
            ".K...K..",
            "K.....K.",
        ], 0, -1),
        'blink_angry': ([
            "........",
            "......KK",
            "...KKK..",
            "KKK.....",
        ], 0, -1),
        'blink_sad': ([
            "........",
            "........",
            "........",
            "KK......",
            "..KKKKKK",
        ], 0, -1),
    },
}

BROW_F = {
    'near': {
        'normal': ["...BBBB..", ".BB....B.", "B........"],
        'smile': (["...BBBB..", ".BB....B.", "B........"], 0, -1),
        'angry': ["BB.......", "..BBB....", ".....BBB.", ".......B."],
        'sad': [".......B.", ".....BB..", "BBBBB...."],
        'surprise': (["..BBBB...", ".B....BB.", "B........"], 0, -2),
    },
    'far': {
        'normal': ["BBBB...", "....BB."],
        'smile': (["BBBB...", "....BB."], 0, -1),
        'angry': ["....BB.", "..BB...", "BB....."],
        'sad': ["BB.....", "..BBB..", ".....BB"],
        'surprise': ([".BBBB..", "B....B."], 0, -2),
    },
}

MOUTH_F = {
    'normal': [".lll.", "..h.."],
    'normal_talk': ["..ll.", ".lDDl", "..ll."],
    'smile': ["l...l", ".lll."],
    'smile_talk': ["lllll", ".lDdl", "..ll."],
    'angry': [".lll.", "l...l"],
    'angry_talk': [".lll.", "lDDDl", ".lll."],
    'sad': ["..l..", ".l.l."],
    'sad_talk': ["..ll.", ".lDDl", ".llll"],
    'surprise': ["..ll."],
    'surprise_talk': ["..ll.", ".lDDl", ".lDDl", "..ll."],
}

EYE_O = {
    'near': {
        'normal': ([
            "...KKKKK.",
            ".KKKK000K",
            "K.W0H01W.",
            "..lW122l.",
            "....ll...",
        ], 0, 1),
        'smile': ([
            "...KKKKK.",
            ".KKKK000K",
            "K.l0H01l.",
            "...llll..",
        ], 0, 1),
        'angry': ([
            ".KKK.....",
            "KKKKKKKK.",
            "K.W0H0KKK",
            "..lW122l.",
            "....ll...",
        ], 0, 1),
        'sad': ([
            "......KK.",
            "..KKKKK0K",
            "KKKW0H01.",
            "..lW122l.",
            "....ll...",
        ], 0, 1),
        'surprise': ([
            "...KKKKK.",
            ".KKwwwwwK",
            "K.W0H01W.",
            "..W0122W.",
            "...llll..",
        ], 0, 0),
        'blink': ([
            ".........",
            ".........",
            "KKKKKKKK.",
            "..llll...",
        ], 0, 1),
        'blink_smile': ([
            ".........",
            "...KKK...",
            ".KK...KK.",
        ], 0, 1),
        'blink_angry': ([
            ".........",
            "KKK......",
            "...KKKKKK",
        ], 0, 1),
        'blink_sad': ([
            ".........",
            "......KK.",
            "KKKKKK...",
        ], 0, 1),
    },
    'far': {
        'normal': ([
            ".KKKK..",
            "K000KKK",
            "WH01W.K",
            "lW12l..",
            ".ll....",
        ], 0, 1),
        'smile': ([
            ".KKKK..",
            "K000KKK",
            "lH01l.K",
            ".lll...",
        ], 0, 1),
        'angry': ([
            "....KK.",
            "..KKKKK",
            "KKK01WK",
            "lW12l..",
            ".ll....",
        ], 0, 1),
        'sad': ([
            "KK.....",
            "K0KKKK.",
            "WH01KKK",
            "lW12l.K",
            ".ll....",
        ], 0, 1),
        'surprise': ([
            ".KKKK..",
            "KwwwwKK",
            "WH01W.K",
            "W012W..",
            ".lll...",
        ], 0, 0),
        'blink': ([
            ".......",
            ".......",
            "KKKKKKK",
            ".lll...",
        ], 0, 1),
        'blink_smile': ([
            ".......",
            "..KKK..",
            "KK...KK",
        ], 0, 1),
        'blink_angry': ([
            ".......",
            ".....KK",
            "KKKKK..",
        ], 0, 1),
        'blink_sad': ([
            ".......",
            "KK.....",
            "..KKKKK",
        ], 0, 1),
    },
}

BROW_O = {
    'near': {
        'normal': (["...BBBBB.", ".BBBBBBBB", "BB......."], 0, 1),
        'smile': (["...BBBBB.", ".BBBBBBBB", "BB......."], 0, 0),
        'angry': (["BBB......", ".BBBBB...", "....BBBBB", "......BBB"], 0, 1),
        'sad': ([".......BB", "....BBBBB", "BBBBBB...", "B........"], 0, 0),
        'surprise': (["...BBBBB.", ".BBBBBBBB", "BB......."], 0, -1),
    },
    'far': {
        'normal': (["BBBBB..", "BBBBBBB", "......B"], 0, 1),
        'smile': (["BBBBB..", "BBBBBBB", "......B"], 0, 0),
        'angry': ([".....BB", "...BBBB", "BBBBB..", "BBB...."], 0, 1),
        'sad': (["BB.....", "BBBBB..", "..BBBBB", ".....BB"], 0, 0),
        'surprise': (["BBBBB..", "BBBBBBB", "......B"], 0, -1),
    },
}

NOSE_M = [".s", "hS"]


def tget(tmpl, key, fallback='normal'):
    t = tmpl.get(key)
    if t is None and '_' in key:
        t = tmpl.get(key.split('_')[0])
    if t is None:
        t = tmpl.get(fallback)
    if isinstance(t, tuple):
        return t
    return (t, 0, 0)


def stamp(rgba, owner, allowed, x0, y0, t, cmap):
    rows, dx, dy = t
    H, W = owner.shape
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch == '.' or ch == ' ':
                continue
            x, y = x0 + dx + c, y0 + dy + r
            if 0 <= x < W and 0 <= y < H and (allowed is None or owner[y, x] in allowed):
                col = cmap.get(ch)
                if col is not None:
                    rgba[y, x] = col


def feature_cmap(skin, eye, hair, brow=(1, 0)):
    sk, ey, hr = ramp(skin), ramp(eye), ramp(hair)
    return {
        'K': INK, 'k': INK2,
        '0': ey[0], '1': ey[1], '2': ey[2], '3': ey[3],
        'W': PAL['grey'][4], 'w': PAL['grey'][3], 'H': PAL['grey'][5],
        'l': sk[0], 'S': sk[1], 's': sk[2], 'h': sk[4], 'n': sk[3],
        'b': hr[brow[0]], 'B': hr[brow[1]],
        'D': PAL['cloth_crimson'][1], 'd': PAL['cloth_crimson'][2], 't': PAL['cloth_crimson'][3],
        'T': PAL['grey'][4],
    }


# ---------------------------------------------------------------- 通用头部
FACE_M = [
    (28.0, 22.5), (40.0, 21.0), (52.5, 20.5), (55.2, 24.5), (55.8, 31.0), (55.1, 35.5), (55.6, 40.0),
    (54.0, 45.0), (50.6, 49.6), (46.6, 52.6, 1), (40.5, 50.6), (34.2, 47.4), (30.2, 43.0),
    (27.4, 36.0), (26.6, 27.0),
]
NECK_M = [(31.0, 40.0), (43.0, 45.0), (42.4, 52.0), (43.6, 60.0), (29.4, 60.0), (30.4, 52.0)]
EAR_M = [(29.6, 33.5), (26.8, 32.2), (24.6, 34.4), (24.3, 38.6), (25.5, 42.2), (27.9, 44.0), (30.0, 42.8)]


def sh_face(far=3, stubble=None, hollow=None, extra=None, cast=('hair',)):
    """脸：远侧(右)背光带、下颌背光、刘海投影；stubble=胡茬区(基准坐标多边形)；hollow=颧下凹陷阴影。"""
    def f(sc, p):
        m = p.mask
        idx = np.full(m.shape, 3, int)
        fk = max(1, int(round(far * sc.s)))
        idx[near_edge(m, 1, 0, fk)] = 2
        idx[near_edge(m, 1, 1, max(1, int(round(2 * sc.s)))) & near_edge(m, 1, 0, int(round(7 * sc.s)))] = 2
        if stubble is not None:
            st = sc.shp(stubble) & m
            idx[st] = np.minimum(idx[st], 2)
            ys, xs = np.nonzero(st & ~near_edge(m, 1, 0, fk) & erode(st, 1))
            for y, x in zip(ys, xs):
                if speckle(x, y, 6, 3):
                    idx[y, x] = 1
        if hollow is not None:
            hm = sc.shp(hollow) & m
            idx[hm] = np.minimum(idx[hm], 2)
        hair = sc.mask_of(groups=cast, after=p)
        idx[m & shift(hair, 1, max(1, int(round(2 * sc.s)))) & ~hair] = 2
        idx[m & shift(hair, 1, 1) & ~hair & near_edge(m, 1, 0, int(round(9 * sc.s)))] = 1
        if extra:
            extra(sc, p, idx)
        return idx
    return f


def sh_neck(sc, p):
    m = p.mask
    idx = np.full(m.shape, 2, int)
    face = sc.mask_of(names=('face',))
    idx[m & shift(face, 1, 3)] = 1
    idx[near_edge(m, 1, 0, 2)] = 1
    return idx


def sh_ear(sc, p):
    m = p.mask
    idx = np.full(m.shape, 3, int)
    inner = erode(m, 1) & ~near_edge(m, -1, 0, 2)
    idx[inner] = 2
    idx[near_edge(m, 1, 1, 1)] = 2
    return idx


def std_head(sc, skin='skin', face=FACE_M, neck=NECK_M, ear=EAR_M, **fkw):
    sc.add('neck', sc.shp(neck), skin, sh_neck, line=0)
    sc.add('face', sc.shp(face), skin, sh_face(**fkw), line=0)
    if ear:
        sc.add('ear', sc.shp(ear), skin, sh_ear, line=0)


def add_strands(sc, hl, strands, rmp, line_u=0.3, **kw):
    hs = hair_strand_shader(hl, **kw)
    for item in strands:
        nm, pts, ws = item[:3]
        opt = item[3] if len(item) > 3 else {}
        p = sc.add_strand(nm, Strand(pts, ws), rmp, hs, line=0, line_same=opt.get('ls', 0), group='hair')
        ys, xs, u, v, N = p.strand.uv(p.mask)
        ok = np.zeros_like(p.mask)
        ok[ys, xs] = u > opt.get('lu', line_u)
        p.same_ok = ok
        p.same_dirs = opt.get('dirs', 'dr')


def stroke(pts, i, only=None):
    """在部件着色后画一条 1px 线（色阶 i），限于部件内。pts 为基准坐标。"""
    def fn(sc, p, idx):
        for x, y in line_px(sc.P(pts)):
            if 0 <= y < sc.h and 0 <= x < sc.w and p.mask[y, x]:
                idx[y, x] = i
    return fn


def folds(sc, name, lines, i=None):
    """给部件追加若干条褶皱/缝线（色阶 i，缺省为该部件基色减一档）。"""
    p = sc.byname[name]
    for pts in lines:
        p.paint.append(stroke(pts, 2 if i is None else i))


RIDGE = ([(40.5, 63.0), (41.2, 71.0), (41.6, 80.0)], [(39.5, 63.0), (40.2, 71.0), (40.6, 80.0)])


def ridge(sc, name, x0=0.0, dark=2, light=4):
    """胸甲中脊：一条暗线 + 左侧一条亮线（3/4 侧面中线偏右）。"""
    p = sc.byname[name]
    p.paint.append(stroke([(x + x0, y) for x, y in RIDGE[0]], dark))
    p.paint.append(stroke([(x + x0, y) for x, y in RIDGE[1]], light))


def band_strand(sc, name, pts, width, rmp, shader, **kw):
    """等宽布条/滚边（金边、绶带等）。"""
    return sc.add_strand(name, Strand(pts, [width] * len(pts)), rmp, shader, **kw)



def sh_cloth(base=3, dark_k=2, light_k=1, cast=()):
    def f(sc, p):
        m = p.mask
        idx = np.full(m.shape, base, int)
        idx[near_edge(m, 1, 1, dark_k)] -= 1
        idx[near_edge(m, -1, -1, light_k)] += 1
        for names, dx, dy in cast:
            occ = sc.mask_of(names=names)
            idx[m & shift(occ, dx, dy) & ~occ] -= 1
        return np.clip(idx, 1, len(p.ramp) - 1)
    return f


L_ORB = np.array([-0.5, -0.55, 0.67])
L_ORB = L_ORB / np.linalg.norm(L_ORB)


def sh_orb(levels=(4, 3, 2, 1), th=(0.55, 0.05, -0.5), w=(0.6, 0.8), c=None, r=None, rim=True,
           spec=None, cast=(), mode='auto'):
    """凸面（金属甲片/鼓起的布）四档明暗，左上亮 → 右下暗。
    mode：'sph' 椭球法线（分档边界是弧线，像真正的圆甲）；'cyl' 竖圆柱（胸甲）；'lin' 线性斜切。
    'auto'：w 横向权重更大时按竖圆柱，否则按椭球。th 的中档阈值折算为整体明暗偏移。"""
    def f(sc, p):
        m = p.mask
        idx = np.full(m.shape, levels[1], int)
        ys, xs = np.nonzero(m)
        full_lit = np.full(m.shape, -9.0)
        thr = th
        if len(ys):
            if c is None:
                cx, cy = (xs.min() + xs.max() + 1) / 2, (ys.min() + ys.max() + 1) / 2
            else:
                cx, cy = sc.X(*c)
            if r is None:
                rx, ry = max(1, (xs.max() - xs.min() + 1) / 2), max(1, (ys.max() - ys.min() + 1) / 2)
            else:
                rx, ry = r[0] * sc.s, r[1] * sc.s
            dx = (xs + 0.5 - cx) / rx
            dy = (ys + 0.5 - cy) / ry
            md = mode
            if md == 'auto':
                md = 'cyl' if w[0] > w[1] + 0.05 else 'sph'
            if md == 'lin':
                lit = -(dx * w[0] + dy * w[1])
            else:
                k = 1.0 if md == 'sph' else 0.45 * w[1] / max(w[0], 1e-6)
                ex, ey = np.clip(dx, -1.5, 1.5), np.clip(dy * k, -1.5, 1.5)
                d2 = ex * ex + ey * ey
                nrm = np.where(d2 > 1, 1 / np.sqrt(np.maximum(d2, 1e-9)), 1.0)
                ex, ey = ex * nrm, ey * nrm
                ez = np.sqrt(np.clip(1 - ex * ex - ey * ey, 0, 1))
                lit = ex * L_ORB[0] + ey * L_ORB[1] + ez * L_ORB[2]
                bias = th[1] * 0.8
                thr = (0.80 + bias, 0.45 + bias, 0.05 + bias)
            v = np.where(lit > thr[0], levels[0],
                         np.where(lit > thr[1], levels[1], np.where(lit > thr[2], levels[2], levels[3])))
            idx[ys, xs] = v
            full_lit[ys, xs] = lit
        if rim:
            e = near_edge(m, 1, 1, 1)
            idx[e] = np.minimum(idx[e], levels[2])
            e = near_edge(m, -1, -1, 1) & (full_lit > thr[2])
            idx[e] = np.maximum(idx[e], levels[1] if levels[1] != levels[0] else levels[0])
        for names, dx_, dy_ in cast:
            occ = sc.mask_of(names=names)
            sh = m & shift(occ, dx_, dy_) & ~occ
            idx[sh] = np.maximum(min(levels), idx[sh] - 1)
        if spec is not None:
            idx[m & spec(sc)] = levels[0]
        return idx
    return f


def sh_beard(base=3, lo=1, hi=4, strokes=True, seed=0):
    """胡须：左上受光，右侧/下缘背光；内部有向下的短发丝笔触。"""
    def f(sc, p):
        m = p.mask
        idx = np.full(m.shape, base, int)
        idx[near_edge(m, 1, 0, 3)] -= 1
        idx[near_edge(m, 0, 1, 2)] -= 1
        idx[near_edge(m, -1, -1, 1) & ~near_edge(m, 1, 0, 4)] += 1
        if strokes:
            ys, xs = np.nonzero(erode(m, 1))
            for y, x in zip(ys, xs):
                if speckle(x, y, 9, seed + 5) and m[min(y + 2, m.shape[0] - 1), x]:
                    idx[y, x] -= 1
                    idx[y + 1, x] -= 1
        return np.clip(idx, lo, hi)
    return f


# ---------------------------------------------------------------- 角色：艾尔文
def build_elwin(sc):
    H = 'hair_ash'
    NV = 'cloth_navy'
    hl = HairLight(38, 26, 21, t1=0.55, t2=0.18,
                   band=arc_band(37, 30, 15.5, 19.0, -172, -40, teeth=2.0, tw=8))
    # ---- 身体：上衣 → 胸甲 → 披风 → 立领（白衬里在颈后，外领在颈前）
    sc.add('torso', sc.shp([(30, 53), (20, 57), (12, 61), (7, 67), (5, 80, 1), (74, 80, 1), (73, 68),
                            (67, 62), (57, 57.5), (45, 54)]), NV, sh_cloth(3), line=0)
    sc.add('plate', sc.shp([(23.5, 66), (30.5, 63.5), (38.5, 65), (46.5, 62.8), (54.5, 64.8),
                            (57.5, 80, 1), (21.5, 80, 1)]), 'steel',
           sh_orb((4, 3, 2, 1), th=(0.55, 0.0, -0.45), w=(0.85, 0.5)), line=0)
    sc.byname['plate'].paint.append(stroke([(40.5, 67.0), (41.2, 73.0), (41.6, 80.0)], 2))
    sc.byname['plate'].paint.append(stroke([(39.5, 67.0), (40.2, 73.0), (40.6, 80.0)], 4))
    band_strand(sc, 'plate_rim', [(23.8, 65.6), (30.5, 63.6), (38.5, 65.1), (46.5, 62.9), (54.4, 64.9)], 2.2,
                'gold', sh_rim(3, dark=((1, 1, 1, 1),), light=((0, -1, 1, 1),)), line=0)
    cape_n = [(28.5, 55.0), (19.0, 57.5), (11.0, 61.5), (6.0, 67.5), (4.0, 80, 1), (19.5, 80, 1),
              (20.0, 71.0), (23.5, 63.0)]
    cape_f = [(46.5, 55.0), (57.0, 57.5), (66.0, 61.5), (72.0, 67.0), (74.5, 80, 1), (60.5, 80, 1),
              (59.5, 70.0), (54.5, 62.0)]
    sc.add('cape_n', sc.shp(cape_n), NV, sh_cloth(2, dark_k=2, light_k=1), line=0)
    sc.add('cape_f', sc.shp(cape_f), NV, sh_cloth(2, dark_k=2, light_k=1), line=0)
    band_strand(sc, 'trim_n', [(23.8, 62.0), (20.6, 70.5), (20.0, 80.5)], 2.0, 'gold',
                sh_rim(3, dark=((1, 0, 1, 1),), light=()), line=0)
    band_strand(sc, 'trim_f', [(54.2, 61.0), (59.8, 70.0), (61.0, 80.5)], 2.0, 'gold',
                sh_rim(3, dark=((1, 0, 1, 1),), light=()), line=0)
    sc.add('collar_back', sc.shp([(27.0, 50.5), (33.0, 47.5), (42.0, 48.0), (48.0, 50.5), (48.5, 57.0),
                                  (27.0, 57.0)]), 'cloth_white', sh_cloth(3, dark_k=1, light_k=0), line=0)
    # ---- 后发（在脸后）
    back = [(23.5, 44.0, 1), (18.5, 35.0), (18.0, 25.0), (21.5, 15.5), (28.5, 9.0), (38.0, 6.5),
            (47.5, 7.5), (55.0, 12.0), (59.0, 19.0), (60.0, 26.0), (58.0, 32.0, 1), (54.0, 26.0),
            (42.0, 24.0), (30.0, 34.0)]
    sc.add('hair_back', sc.shp(back), H, hair_mass_shader(hl), line=0, group='hair')
    add_strands(sc, hl, [
        ('k3', [(23, 18), (17.5, 23), (13.5, 29)], [9, 6, 0]),
        ('k1', [(23.5, 26), (18.5, 33), (15.5, 40)], [10, 7, 0]),
        ('k2', [(26, 32), (22.5, 39.5), (21, 46)], [9, 6, 0]),
    ], H, tip=0.8)
    std_head(sc)
    sc.add('collar', sc.shp([(26.5, 54.5), (30.5, 56.8), (36.5, 58.8), (41.5, 58.3), (45.5, 55.8),
                             (48.8, 53.0), (49.6, 57.2), (45.2, 61.6), (38.0, 63.2), (31.0, 61.8),
                             (26.4, 58.6)]), NV, sh_cloth(3, dark_k=1, light_k=1), line=0)
    band_strand(sc, 'collar_rim', [(26.8, 55.0), (30.8, 57.2), (36.5, 59.2), (41.5, 58.7), (45.6, 56.2),
                                   (48.8, 53.4)], 1.2, 'gold', sh_flat(3), line=None, outer=None)
    sc.add('clasp', sc.ell(24.2, 62.6, 2.6, 2.6), 'gold',
           sh_rim(3, dark=((1, 1, 1, 1),), light=((-1, -1, 1, 1),)), line=0)
    sc.overlays.append((23.5, 61.5, ["bB", "BB"], {'b': PAL['magic_blue'][3], 'B': PAL['magic_blue'][2]}))
    folds(sc, 'cape_n', [[(11.5, 65.5), (12.8, 72.5), (12.6, 80.0)], [(7.4, 71.0), (7.8, 80.0)]], 1)
    folds(sc, 'cape_f', [[(67.0, 65.0), (66.0, 72.5), (66.4, 80.0)], [(71.6, 71.0), (71.4, 80.0)]], 1)
    # ---- 前发
    add_strands(sc, hl, [
        ('t2', [(33, 13), (27.5, 8), (22, 6.5)], [10, 7, 0]),
        ('t3', [(45, 12), (51.5, 8), (57.5, 9)], [9, 6, 0]),
        ('t1', [(39, 12), (42, 6), (47, 2.5)], [9, 6, 0]),
        ('b5', [(48, 11), (53, 15), (57, 19.5), (60, 24)], [10, 8, 5, 0]),
        ('b1', [(29, 15), (27, 22.5), (26.5, 29.5), (27.5, 35.5)], [9, 7, 4, 0]),
        ('b4', [(44, 10), (46.5, 15.5), (49, 20.5), (51, 25)], [10, 8, 5, 0]),
        ('b2', [(33, 11), (31.5, 17), (32.5, 22), (34.5, 25.5)], [10, 9, 6, 0]),
        ('bm', [(41, 12), (43, 18.5), (44.5, 24.5), (45, 30)], [8, 7, 4, 0]),
        ('b3', [(37.5, 10), (38, 16), (39.5, 21), (41.5, 25)], [10, 9, 6, 0]),
    ], H, tip=0.8)


# ---------------------------------------------------------------- 角色：诺拉
FACE_F = [
    (28.0, 22.5), (40.0, 21.0), (52.5, 20.5), (55.0, 24.5), (55.6, 31.0), (55.0, 35.5), (55.3, 39.5),
    (53.6, 44.5), (50.2, 48.8), (46.4, 51.6, 1), (40.6, 49.8), (34.6, 46.8), (30.6, 42.6),
    (27.6, 36.0), (26.8, 27.0),
]
NECK_F = [(31.6, 40.0), (42.6, 44.5), (41.8, 51.0), (43.0, 60.0), (30.2, 60.0), (31.2, 51.0)]
FACE_FY = [   # 更稚气：下半脸更圆、下巴略短
    (28.0, 22.5), (40.0, 21.0), (52.5, 20.5), (55.2, 24.5), (55.8, 31.0), (55.4, 35.5), (55.8, 40.0),
    (54.4, 45.0), (51.0, 49.0), (46.6, 51.2, 1), (40.4, 49.8), (34.2, 47.2), (30.4, 43.4),
    (27.6, 36.0), (26.8, 27.0),
]
FACE_FM = [   # 更成熟：面颊更瘦、下巴略长
    (28.0, 22.5), (40.0, 21.0), (52.5, 20.5), (54.8, 24.5), (55.4, 31.0), (54.8, 35.5), (55.0, 39.5),
    (53.2, 44.5), (50.0, 49.4), (46.6, 52.6, 1), (40.8, 50.4), (34.8, 47.0), (30.8, 42.4),
    (27.6, 36.0), (26.8, 27.0),
]


def build_nora(sc):
    H = 'hair_brown'
    G = 'cloth_green'
    hl = HairLight(38, 26, 20.5, t1=0.5, t2=0.12, band=arc_band(37, 30, 15.0, 18.5, -172, -45))
    # ---- 身后：远侧肩后露出的箭羽、箭袋
    for i, (x0, y0, x1, y1) in enumerate([(58.5, 64, 60.5, 47.5), (62.5, 64, 66.5, 46.5), (66, 64, 71, 49.5)]):
        sc.add('shaft%d' % i, sc.st(Strand([(x0, y0), (x1, y1)], [1.6, 1.6]))[1], 'wood', sh_flat(3), line=0)
    for i, (x, y, rot) in enumerate([(60.8, 47.0, 0.12), (66.9, 46.2, 0.25), (71.4, 49.3, 0.4)]):
        c, s_ = math.cos(rot), math.sin(rot)
        pts = [(0, -4.2), (2.3, -1.2), (2.3, 3.6), (0, 2.0), (-2.3, 3.6), (-2.3, -1.2)]
        pts = [(x + px * c - py * s_, y + px * s_ + py * c) for px, py in pts]
        rm = 'cloth_white' if i != 1 else 'cloth_crimson'
        sc.add('fletch%d' % i, sc.poly(pts), rm, sh_rim(3, dark=((1, 0, 1, 1),), light=()), line=0)
    sc.add('quiver', sc.shp([(55.5, 60.5, 1), (57, 56), (68.5, 57.5), (70, 62, 1)]), 'leather',
           sh_rim(3, dark=((1, 1, 1, 1),), light=((0, -1, 1, 1),)), line=0)
    # ---- 马尾（在头后，垂在颈后）
    add_strands(sc, hl, [
        ('tail', [(24, 13), (18.5, 16), (15.5, 23), (15, 32), (16.5, 41), (19.5, 48)],
         [8, 8.5, 8, 6.5, 4, 0], {'lu': 0.5}),
    ], H, tip=0.85)
    folds(sc, 'tail', [[(16.6, 22.0), (15.0, 30.0), (15.8, 38.0)]], 2)
    folds(sc, 'tail', [[(19.6, 17.4), (17.4, 22.0)]], 4)
    # ---- 身体
    sc.add('torso', sc.shp([(31, 53), (22, 56.5), (14, 60.5), (9, 66), (7, 80, 1), (72, 80, 1), (70, 67),
                            (65, 61.5), (56, 57.5), (44, 54)]), 'earth', sh_cloth(3), line=0)
    sc.add('vest', sc.shp([(22, 60.5), (29.5, 60.5), (35.5, 66.5), (39.5, 72), (41.5, 80, 1), (16, 80, 1),
                           (18, 68)]), 'leather', sh_cloth(3), line=0)
    sc.add('vest_f', sc.shp([(47.5, 58.5), (56, 59.5), (62, 66), (63, 80, 1), (44.5, 80, 1), (43.5, 71),
                             (45, 63)]), 'leather', sh_cloth(3), line=0)
    band_strand(sc, 'strap', [(57, 57.5), (47, 65.5), (35.5, 73.5), (27, 81)], 3.0, 'leather',
                sh_rim(2, dark=((1, 1, 1, 1),), light=((0, -1, 1, 1),)), line=0)
    sc.add('buckle', sc.poly([(43.2, 66.6), (46.8, 66.6), (46.8, 70.2), (43.2, 70.2)]), 'gold',
           sh_rim(3, dark=((1, 1, 1, 1),), light=((-1, -1, 1, 1),)), line=0)
    sc.add('cloak_n', sc.shp([(26.5, 54.5), (17, 57.5), (10, 62), (6, 68), (4.5, 80, 1), (16.5, 80, 1),
                              (17.5, 71), (21.5, 63)]), G, sh_cloth(3, dark_k=2, light_k=1), line=0)
    sc.add('cloak_f', sc.shp([(49, 54.5), (58, 57.5), (66, 62), (71, 68), (73, 80, 1), (61, 80, 1),
                              (59, 71), (55, 62)]), G, sh_cloth(3, dark_k=2, light_k=1), line=0)
    sc.add('hood', sc.shp([(23.5, 53), (25.5, 48.5), (32, 46.5), (43, 47), (50, 49), (54, 53.5),
                           (52, 58.5), (46, 57.2), (33, 57.2), (23, 58)]), G,
           sh_cloth(2, dark_k=1, light_k=1), line=0)
    # ---- 后发
    back = [(24.5, 42.0, 1), (19.5, 33.0), (19.0, 24.0), (22.5, 15.0), (29.5, 9.5), (38.5, 7.5),
            (47.5, 9.0), (54.5, 14.0), (58.0, 21.0), (58.5, 28.0), (57.0, 33.0, 1), (53.0, 25.0),
            (41.0, 23.0), (29.0, 32.0)]
    sc.add('hair_back', sc.shp(back), H, hair_mass_shader(hl), line=0, group='hair')
    sc.add('tie', sc.st(Strand([(21.5, 11.5), (19.5, 17.5)], [3, 3]))[1], 'cloth_green', sh_flat(2),
           line=0, group='tie')
    std_head(sc, face=FACE_F, neck=NECK_F)
    folds(sc, 'vest', [[(28.0, 62.4), (33.4, 67.6), (37.0, 73.0), (38.6, 80.0)]], 2)
    folds(sc, 'vest_f', [[(48.4, 60.6), (46.0, 67.0), (45.6, 80.0)]], 2)
    folds(sc, 'cloak_n', [[(10.4, 66.0), (11.2, 73.0), (10.8, 80.0)]], 2)
    folds(sc, 'cloak_f', [[(67.0, 66.0), (66.0, 73.0), (66.4, 80.0)]], 2)
    sc.add('brooch', sc.ell(30.0, 58.2, 1.8, 1.8), 'gold',
           sh_rim(3, dark=((1, 1, 1, 1),), light=((-1, -1, 1, 1),)), line=0)
    # ---- 前发（向右侧分）
    add_strands(sc, hl, [
        ('f1', [(53, 16), (56, 22), (57, 30), (56.5, 38)], [8, 6, 4, 0]),
        ('n1', [(29, 16), (26.5, 23), (26, 32), (27.5, 41)], [8, 6, 4, 0]),
        ('n2', [(32, 14), (29.5, 19), (28.5, 24.5)], [9, 7, 0]),
        ('s3', [(45, 13), (50.5, 15), (54.5, 19), (57, 23.5)], [9, 8, 5, 0]),
        ('s2', [(40, 13), (44.5, 15.5), (48, 19.5), (50.5, 24.5)], [10, 9, 6, 0]),
        ('s4', [(36, 15), (40, 19.5), (42.5, 25), (44, 31)], [8, 7, 5, 0]),
        ('s1', [(34, 14), (37, 17), (40, 21), (42, 25.5)], [10, 9, 6, 0]),
    ], H, tip=0.85)


# ---------------------------------------------------------------- 角色：格伦
FACE_O = [
    (28.0, 22.5), (40.0, 21.0), (52.5, 20.5), (55.2, 24.5), (55.8, 31.0), (55.2, 35.5), (55.8, 40.0),
    (55.0, 45.5), (52.0, 50.5), (47.5, 53.8, 1), (41.0, 52.2), (34.5, 49.0), (30.4, 44.5),
    (27.4, 36.0), (26.6, 27.0),
]
NECK_O = [(31.0, 40.0), (44.0, 45.0), (43.4, 52.0), (44.6, 60.0), (29.4, 60.0), (30.4, 52.0)]

def build_glenn(sc):
    H = 'hair_grey'
    ST = 'steel'
    hl = HairLight(38, 27, 20, base=3, lo=1, hi=4, t1=0.5, t2=0.1,
                   band=arc_band(37, 31, 15.5, 18.5, -165, -60))
    # ---- 披风（身后）→ 胸甲 → 肩甲 → 护颈
    sc.add('cape', sc.shp([(22, 55), (9, 61), (3.5, 69), (2, 80, 1), (78, 80, 1), (76.5, 69), (71, 61),
                           (58, 55)]), 'cloth_green', sh_cloth(2, dark_k=2, light_k=1), line=0)
    sc.add('chest', sc.shp([(22, 60), (57, 59), (61, 80, 1), (19, 80, 1)]), ST,
           sh_orb((4, 3, 2, 1), th=(0.5, 0.0, -0.45), w=(0.8, 0.5), cast=((('gorget',), 1, 2),)), line=0)
    ridge(sc, 'chest', 1.0)
    sc.add('badge', sc.shp([(29.5, 66.5, 1), (35.5, 66.5, 1), (35.5, 70.5), (32.5, 73.5, 1), (29.5, 70.5)]),
           'gold', sh_orb((4, 3, 2, 1)), line=0)
    sc.overlays.append((31.0, 67.5, ["w.w", "www", ".w."], {'w': PAL['cloth_white'][4]}))
    folds(sc, 'cape', [[(5.0, 70.0), (4.6, 80.0)], [(75.0, 70.0), (75.4, 80.0)]], 1)
    for side, pts, trim in [
            ('f', [(49.5, 55.5), (60, 56.5), (68, 60.5), (72.5, 67), (71, 73), (64, 71.5), (57, 66), (51, 61.5)],
             [(57.5, 66.2), (64.2, 71.6), (71.2, 73.0)]),
            ('n', [(29.5, 55.5), (18, 56.5), (9.5, 60.5), (5, 67), (6.5, 73.5), (14, 72), (21, 66.5), (28, 61.5)],
             [(6.8, 73.4), (14, 72.0), (21.2, 66.4), (27.8, 61.8)])]:
        sc.add('pauld_' + side, sc.shp(pts), ST, sh_orb((4, 3, 2, 1), th=(0.45, 0.0, -0.5)), line=0)
        band_strand(sc, 'ptrim_' + side, trim, 2.0, 'gold', sh_rim(3, dark=((0, 1, 1, 1),), light=()), line=0)
    sc.add('gorget', sc.shp([(28.5, 52), (33, 55.2), (40, 56.6), (46.5, 54.6), (49.5, 51.5), (51.5, 57),
                             (46.5, 61.2), (39, 62.4), (32, 61), (27, 57.5)]), ST,
           sh_orb((4, 3, 2, 1), th=(0.4, -0.1, -0.6), w=(0.9, 0.4)), line=0)
    # ---- 头
    back = [(25.0, 41.0, 1), (20.0, 33.0), (19.5, 24.0), (23.0, 15.5), (30.0, 10.5), (39.0, 9.0),
            (48.0, 10.5), (54.5, 15.0), (57.5, 21.5), (57.5, 28.0), (56.0, 31.0, 1), (53.0, 24.0),
            (41.0, 22.5), (29.5, 30.0)]
    sc.add('hair_back', sc.shp(back), H, hair_mass_shader(hl), line=0, group='hair')
    add_strands(sc, hl, [
        ('gk1', [(24, 22), (20.5, 28), (20, 34)], [8, 6, 0]),
        ('gk2', [(26, 29), (23, 35), (23.5, 40)], [8, 6, 0]),
    ], H, tip=0.8)
    std_head(sc, 'skin_old', face=FACE_O, neck=NECK_O)
    beard = [(28.6, 33.0), (30.0, 39.0), (32.5, 43.0), (36.5, 45.0), (40.5, 44.2), (44.5, 43.2), (48.5, 44.0),
             (52.0, 42.5), (55.6, 38.6), (56.6, 44.5), (54.8, 50.0), (51.5, 54.5), (50.0, 54.0),
             (48.5, 57.2, 1), (46.0, 56.4), (44.0, 58.4, 1), (41.5, 56.2), (39.0, 57.0, 1), (37.0, 54.8),
             (33.0, 52.0), (29.5, 47.5), (27.4, 40.0)]
    sc.add('beard', sc.shp(beard), H, sh_beard(3), line=0, group='beard')
    sc.add('mustache', sc.shp([(40.0, 46.0), (42.0, 43.8), (45.0, 42.8), (48.0, 43.2), (50.6, 44.8),
                               (52.0, 47.6, 1), (49.0, 46.4), (45.5, 46.0), (42.0, 46.8), (39.2, 48.2, 1)]),
           H, sh_beard(3, strokes=False), line=0, group='mustache')
    add_strands(sc, hl, [
        ('g1', [(30, 15), (28, 20), (27.5, 27)], [9, 7, 0]),
        ('g4', [(47, 12), (52, 15.5), (55.5, 21)], [9, 7, 0]),
        ('g2', [(34, 12), (35, 17), (37.5, 22.5)], [10, 8, 0]),
        ('g3', [(40, 11), (44, 15), (48, 21)], [10, 8, 0]),
    ], H, tip=0.85)


# ---------------------------------------------------------------- 通用小件
FACE_B = [
    (28.0, 22.5), (40.0, 21.0), (52.5, 20.5), (55.4, 24.5), (56.2, 31.0), (55.8, 35.5), (56.6, 40.0),
    (56.4, 46.0), (54.0, 51.5), (48.5, 55.0, 1), (41.0, 54.0), (34.0, 51.5), (29.8, 47.0),
    (27.0, 36.0), (26.4, 27.0),
]
NECK_B = [(29.5, 40.0), (45.0, 45.0), (45.5, 52.0), (47.0, 60.0), (27.5, 60.0), (28.5, 52.0)]
FACE_G = [
    (28.5, 22.5), (40.0, 21.0), (52.0, 20.5), (54.6, 24.5), (55.2, 31.0), (54.6, 35.0), (55.0, 39.0),
    (53.6, 44.0), (51.6, 48.5), (47.0, 54.0, 1), (41.0, 52.4), (35.0, 49.0), (31.0, 44.0),
    (28.0, 36.0), (27.2, 27.0),
]


def ring_px(cx, cy, rx, ry, n=56):
    pts = [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n))
           for i in range(n + 1)]
    return line_px(pts)


def gold_cmap():
    g = PAL['gold']
    return {'G': g[3], 'g': g[2], 'd': g[1], 'y': g[4], 'W': PAL['cloth_white'][4], 'w': PAL['cloth_white'][2],
            'K': INK, 'k': PAL['cloth_black'][2], 'r': PAL['cloth_crimson'][3], 'R': PAL['cloth_crimson'][2]}


# 黑鹰纹章（展翅鹰）
EAGLE = [
    "k.........k",
    "kk...k...kk",
    ".kkk.kk.kkk",
    "..kkkkkkkk.",
    "...kkkkkk..",
    "....kkkk...",
    "...k.kk.k..",
]
EAGLE_SCRATCHED = [
    "k.........k",
    "kk...k...x.",
    ".kkx.kk.kkk",
    "..kkxkkkk..",
    "...kkxkkk..",
    "....kkxk...",
    "...k.kkx...",
]
PENDANT_STAG = [
    ".dGd.",
    "dW.Wd",
    "G.W.G",
    "d.W.d",
    ".dgd.",
]


# ---------------------------------------------------------------- 角色：赛琳
def build_serin(sc):
    H = 'hair_black'
    W_ = 'cloth_white'
    SK = 'cloth_sky'
    hl = HairLight(38, 27, 20.5, t1=0.45, t2=0.05, band=arc_band(37, 31, 13.5, 16.5, -170, -40))
    sc.add('veil_back', sc.shp([(22, 14), (31, 6.5), (44, 5.5), (55, 10), (61.5, 20), (64, 34), (66, 50),
                                (68, 62, 1), (55.5, 61, 1), (53, 48), (51, 36), (40, 30), (30, 36), (28, 50),
                                (25, 62, 1), (11, 62, 1), (11.5, 48), (13.5, 32)]), W_,
           sh_cloth(2, dark_k=3, light_k=1), line=0, group='veil')
    folds(sc, 'veil_back', [[(15.6, 30.0), (14.2, 42.0), (13.4, 56.0)], [(20.0, 38.0), (19.2, 50.0), (19.6, 60.0)],
                            [(60.4, 28.0), (62.4, 40.0), (64.0, 54.0)], [(57.0, 40.0), (58.2, 52.0), (58.6, 60.0)]], 1)
    sc.add('hair_long', sc.shp([(22, 24), (18.5, 38), (17.5, 52), (19, 61, 1), (28, 60, 1), (30, 46),
                                (30, 30)]), H, hair_mass_shader(hl), line=0, group='hair')
    sc.add('robe', sc.shp([(31, 53), (21, 56.5), (13, 60.5), (8, 66), (6, 80, 1), (73, 80, 1), (71, 67),
                           (66, 61), (57, 57), (45, 54)]), W_, sh_cloth(3), line=0)
    band_strand(sc, 'robe_band', [(39.5, 64), (40.5, 72), (41, 81)], 3.0, SK, sh_cloth(3, dark_k=1), line=0)
    sc.add('capelet', sc.shp([(28, 54.5), (18, 57.5), (10.5, 62.5), (7.5, 69.5), (12, 72.5), (24, 70.5),
                              (38, 72), (52, 70.5), (65.5, 72.5), (70, 68.5), (67.5, 62), (60, 57.5),
                              (50, 54.5)]), W_, sh_orb((4, 3, 2, 1), th=(0.5, -0.05, -0.55), w=(0.7, 0.7)),
           line=0)
    band_strand(sc, 'cape_trim', [(7.8, 69.2), (12, 72.2), (24, 70.2), (38, 71.7), (52, 70.2), (65.5, 72.2),
                                  (70, 68.2)], 2.0, SK, sh_cloth(3, dark_k=1, light_k=0), line=0)
    folds(sc, 'capelet', [[(18.0, 62.0), (16.4, 68.6)], [(61.6, 62.0), (63.6, 68.6)], [(30.0, 64.0), (29.0, 69.0)]], 2)
    folds(sc, 'robe', [[(20.0, 75.0), (19.2, 80.0)], [(60.0, 75.0), (60.8, 80.0)]], 2)
    add_strands(sc, hl, [('lock_f', [(55, 22), (57.5, 32), (58.5, 44), (58.5, 56)], [6, 7, 6, 0])], H, tip=0.85)
    std_head(sc, face=FACE_F, neck=NECK_F)
    sc.add('collar', sc.shp([(29, 53.5), (33, 56.2), (39.5, 57.4), (45.5, 55.6), (48.8, 52.6), (49.8, 56.6),
                             (45.5, 60.4), (39, 61.6), (32, 60.4), (28, 57.2)]), W_,
           sh_cloth(3, dark_k=1, light_k=1), line=0)
    band_strand(sc, 'collar_trim', [(28.4, 57.0), (32, 60.2), (39, 61.4), (45.5, 60.2), (49.6, 56.4)], 1.6,
                SK, sh_flat(3), line=None, outer=None)
    sc.overlays.append((38, 64, PENDANT_STAG, gold_cmap()))
    add_strands(sc, hl, [
        ('lock_n', [(28.5, 20), (26, 30), (25, 42), (25.5, 54), (27.5, 66)], [7, 8, 8, 6, 0]),
        ('bn6', [(54, 18.5), (56, 23), (57, 28)], [6, 5, 0]),
        ('bn1', [(30, 17), (29, 22), (28.5, 27)], [7, 6, 0]),
        ('bn5', [(49.5, 16), (51, 20.5), (52, 25.5)], [7, 6.5, 0]),
        ('bn2', [(34.5, 15.5), (34, 20.5), (34.5, 25.5)], [7, 6.5, 0]),
        ('bn4', [(44.5, 15), (45.5, 20), (46, 25.5)], [7, 6.5, 0]),
        ('bn3', [(39.5, 15), (40, 20), (40.5, 25.5)], [7, 6.5, 0]),
    ], H, tip=0.8)
    sc.add('veil', sc.shp([(23.5, 26, 1), (21, 17), (26, 9.5), (36, 5.5), (47, 6), (55.5, 10.5), (60, 18),
                           (60.5, 26, 1), (56.8, 21.5), (51.5, 17.2), (44, 15.2), (36, 15.2), (30, 17.6),
                           (26.6, 21.5)]), W_, sh_orb((4, 3, 2, 1), th=(0.3, -0.25, -0.7)), line=0,
           group='veil')
    band_strand(sc, 'veil_trim', [(24.2, 25.4), (27, 19.8), (32, 16.6), (38, 15.4), (44, 15.4), (51, 17.4),
                                  (56.6, 21.2), (59.8, 25.6)], 1.8, SK, sh_flat(3), line=0)


# ---------------------------------------------------------------- 角色：多兰
def sh_buzz(hl):
    """寸头：球面明暗 + 细碎发茬点。"""
    base = hair_mass_shader(hl, rim=1)

    def f(sc, p):
        idx = base(sc, p)
        ys, xs = np.nonzero(p.mask)
        for y, x in zip(ys, xs):
            if speckle(x, y, 9, 1):
                idx[y, x] = max(hl.lo, idx[y, x] - 1)
        return idx
    return f


def build_doran(sc):
    H = 'hair_brown'
    IR = 'iron'
    OL = 'cloth_olive'
    hl = HairLight(38, 26, 19, base=2, lo=1, hi=3, t1=0.45, t2=-0.05,
                   band=arc_band(37, 30, 15.5, 17.5, -160, -70))
    sc.add('under', sc.shp([(28, 53), (16, 57), (6, 62), (2, 69), (1, 80, 1), (79, 80, 1), (78, 69), (74, 62),
                            (62, 57), (50, 53)]), 'cloth_brown', sh_cloth(2), line=0)
    sc.add('tabard', sc.shp([(25, 60), (55, 59), (58, 80, 1), (22, 80, 1)]), OL,
           sh_cloth(3, dark_k=2, light_k=1, cast=((('gorget',), 1, 2),)), line=0)
    sc.overlays.append((35, 66, EAGLE_SCRATCHED, {'k': PAL['cloth_black'][2], 'x': PAL['cloth_olive'][4]}))
    folds(sc, 'tabard', [[(29.5, 66.0), (28.6, 73.0), (28.4, 80.0)], [(51.0, 66.0), (52.0, 73.0), (52.4, 80.0)]], 2)
    for side, pts, lame in [
            ('f', [(51, 54), (63, 55), (72, 59.5), (77.5, 66), (76.5, 74), (68, 72.5), (60, 67), (53, 61)],
             [(56.5, 64.5), (64, 69), (72.5, 70.2), (77.2, 69.6)]),
            ('n', [(28, 54), (15, 55), (6, 59.5), (1.5, 66), (2.5, 74.5), (11, 73), (19, 67), (26.5, 61)],
             [(2.2, 70.6), (10, 69.6), (18, 64.6), (24.5, 59.6)])]:
        sc.add('pauld_' + side, sc.shp(pts), IR, sh_orb((4, 3, 2, 1), th=(0.4, -0.05, -0.55)), line=0)
        band_strand(sc, 'lame_' + side, lame, 1.2, IR, sh_flat(1), line=None, outer=None)
    sc.add('gorget', sc.shp([(27, 51.5), (32, 55.5), (40.5, 57.2), (48, 55), (51.5, 51), (53.5, 57.5),
                             (48, 62.5), (40, 63.8), (32, 62.5), (25.5, 58)]), IR,
           sh_orb((4, 3, 2, 1), th=(0.35, -0.15, -0.6), w=(0.9, 0.4)), line=0)
    rv = {'h': PAL['iron'][4], 'd': PAL['iron'][1]}
    for x, y in [(9.0, 62.0), (16.0, 58.5), (22.5, 57.5), (58.0, 57.5), (65.0, 59.0), (71.0, 62.5)]:
        sc.overlays.append((x, y, ["h", "d"], rv))
    std_head(sc, face=FACE_B, neck=NECK_B, stubble=STUBBLE_B)
    cap = [(26.2, 35.0, 1), (22.0, 30.5), (21.6, 22.5), (24.8, 16.0), (31.5, 12.2), (40.0, 11.2), (48.8, 12.4),
           (54.8, 16.6), (57.0, 22.0), (56.4, 26.8, 1), (54.6, 24.2), (51.8, 22.6), (48.0, 23.0), (43.5, 22.2),
           (38.5, 22.4), (34.0, 23.0), (31.0, 24.2), (29.0, 27.8), (28.0, 31.5)]
    sc.add('hair', sc.shp(cap), H, sh_buzz(hl), line=None, group='hair')


STUBBLE_B = [(29.0, 38.0), (30.8, 44.0), (34.6, 49.0), (40.4, 52.6), (47.6, 55.4), (53.0, 52.0), (56.2, 46.0),
             (56.8, 40.5), (53.4, 43.4), (49.6, 45.0), (47.0, 42.6), (42.8, 43.4), (38.0, 44.8), (33.0, 42.4)]


# ---------------------------------------------------------------- 角色：希德
MOUTH_S = dict(MOUTH_M)
MOUTH_S.update({
    'normal': ["....l", ".lll.", "..s.."],
    'normal_talk': ["....l", ".lDDl", "..ll."],
    'smile': ["l...l", ".lTl.", "..l.."],
    'smile_talk': ["l...ll", "lTTTl.", ".lDl..", "..l..."],
})


def build_sid(sc):
    H = 'hair_red'
    LE = 'leather'
    TE = 'cloth_teal'
    hl = HairLight(38, 25, 21, t1=0.5, t2=0.12, band=arc_band(37, 29, 15.5, 19.0, -170, -40))
    sc.add('dagger_grip', sc.st(Strand([(58.5, 55.5), (64.6, 45.0)], [3.0, 3.0]))[1], 'leather',
           sh_rim(3, dark=((1, 0, 1, 1),), light=()), line=0)
    sc.byname['dagger_grip'].paint.append(stroke([(60.4, 53.2), (64.0, 47.0)], 1))
    sc.add('dagger_pommel', sc.ell(65.4, 43.6, 2.2, 2.2), 'steel', sh_orb((4, 3, 2, 1)), line=0)
    sc.add('dagger_guard', sc.st(Strand([(54.8, 52.4), (62.4, 57.0)], [2.6, 2.6]))[1], 'steel',
           sh_rim(3, dark=((0, 1, 1, 1),), light=((0, -1, 1, 1),)), line=0)
    sc.add('shirt', sc.shp([(30, 55), (49, 55), (51, 80, 1), (28, 80, 1)]), 'cloth_black', sh_cloth(3), line=0)
    sc.add('jacket_n', sc.shp([(29, 53), (19, 57), (11, 61.5), (6.5, 67), (5, 80, 1), (34, 80, 1), (35, 70),
                               (33.5, 62)]), LE, sh_cloth(3), line=0)
    sc.add('jacket_f', sc.shp([(49, 53), (58, 57), (66, 61.5), (70.5, 67), (72, 80, 1), (46.5, 80, 1),
                               (45.5, 70), (47, 62)]), LE, sh_cloth(3), line=0)
    sc.add('lapel_n', sc.shp([(26, 56), (32.5, 59.5), (36, 71, 1), (30.5, 66.5), (22.5, 59.5)]), LE,
           sh_cloth(4, dark_k=1, light_k=0), line=0)
    sc.add('lapel_f', sc.shp([(52, 55), (46.5, 59), (44.8, 70, 1), (49.5, 66), (55.5, 58.5)]), LE,
           sh_cloth(3, dark_k=1, light_k=0), line=0)
    band_strand(sc, 'belt', [(9, 77), (40, 79.5), (70, 77)], 2.0, 'leather', sh_flat(1), line=0)
    folds(sc, 'jacket_n', [[(17.5, 60.5), (19.5, 68.0), (20.5, 76.0)], [(11.0, 66.0), (12.0, 75.0)]], 2)
    folds(sc, 'jacket_f', [[(62.0, 61.5), (60.0, 69.0), (59.6, 76.0)]], 2)
    sc.overlays.append((38.0, 77.5, ["GGG", "G.G"], {'G': PAL['gold'][3]}))
    back = [(23.0, 42.0, 1), (18.0, 33.0), (17.5, 23.0), (21.5, 14.0), (29.0, 8.0), (38.5, 5.5), (48.0, 7.0),
            (55.5, 11.5), (59.5, 19.0), (60.0, 26.0), (58.0, 32.0, 1), (54.0, 25.0), (42.0, 24.0),
            (30.0, 34.0)]
    sc.add('hair_back', sc.shp(back), H, hair_mass_shader(hl), line=0, group='hair')
    add_strands(sc, hl, [
        ('sk1', [(22, 18), (15.5, 20), (10, 23.5)], [9, 6, 0]),
        ('sk2', [(22.5, 26), (16.5, 30.5), (12.5, 36)], [9, 6, 0]),
        ('sk3', [(25, 33), (20.5, 39), (18.5, 45)], [8, 5, 0]),
    ], H, tip=0.8)
    std_head(sc)
    sc.add('scarf', sc.shp([(25.5, 52.5), (30.5, 48.8), (39.5, 51.2), (46.5, 49.4), (52.0, 51.6), (53.0, 57.0),
                            (47.0, 60.2), (38.5, 61.4), (30.0, 60.0), (24.8, 56.6)]), TE,
           sh_orb((4, 3, 2, 1), th=(0.45, -0.05, -0.55), w=(0.6, 0.8)), line=0)
    sc.add('scarf_end', sc.shp([(28.5, 58.5), (33.5, 59.5), (33.0, 66.0), (31.0, 72.5, 1), (29.6, 69.6),
                                (28.0, 73.0, 1), (26.4, 70.0), (25.0, 72.5, 1), (25.6, 64.0)]), TE,
           sh_cloth(3, dark_k=2, light_k=1), line=0)
    band_strand(sc, 'scarf_fold', [(31.5, 52.8), (38.8, 55.2), (46.5, 53.6)], 1.0, TE, sh_flat(1),
                line=None, outer=None)
    add_strands(sc, hl, [
        ('st1', [(30, 12), (26, 5.5), (21.5, 2)], [9, 6, 0]),
        ('st4', [(52, 13), (58, 11), (63, 13)], [8, 5, 0]),
        ('st3', [(46, 10), (51.5, 5), (57, 3.5)], [9, 6, 0]),
        ('st2', [(38, 10), (39, 4), (42, 0.5)], [9, 6, 0]),
        ('sf1', [(55, 17), (60, 21), (63.5, 27)], [8, 6, 0]),
        ('sb1', [(29, 15), (26.5, 22.5), (25.5, 30.5)], [8, 6, 0]),
        ('sb6', [(51, 13.5), (55.5, 18), (58.5, 25.5)], [8, 6, 0]),
        ('sb5', [(46, 12), (50.5, 17), (54, 24)], [9, 7, 0]),
        ('sb2', [(33, 13), (32.5, 19), (34, 26)], [9, 7, 0]),
        ('sb4', [(42, 12.5), (45, 19), (47.5, 29)], [8, 6, 0]),
        ('sb3', [(38, 12), (39.5, 18.5), (42.5, 25)], [9, 7, 0]),
    ], H, tip=0.8)


# ---------------------------------------------------------------- 角色：米拉
def mira_glasses(sc, rgba, expr, frame):
    fr = PAL['gold'][1]
    gl = PAL['grey'][5]
    H, W = rgba.shape[:2]
    pts = []
    for cx, cy, rx, ry in [(35.8, 33.6, 5.3, 5.2), (50.8, 33.6, 3.9, 5.0)]:
        X, Y = sc.X(cx, cy)
        pts += ring_px(X, Y, rx * sc.s, ry * sc.s)
    a = sc.X(41.2, 33.0)
    b = sc.X(46.8, 33.0)
    pts += line_px([a, b])
    pts += line_px([sc.X(30.4, 33.2), sc.X(26.8, 32.6)])
    for x, y in pts:
        if 0 <= x < W and 0 <= y < H and rgba[y, x, 3]:
            rgba[y, x] = fr
    for gx, gy in [(33.2, 30.6), (34.2, 29.6), (48.9, 30.4)]:
        x, y = sc.X(gx, gy)
        x, y = int(x), int(y)
        if 0 <= x < W and 0 <= y < H:
            rgba[y, x] = gl


def build_mira(sc):
    H = 'hair_lav'
    TE = 'cloth_teal'
    hl = HairLight(38, 27, 20.5, t1=0.45, t2=0.05, band=arc_band(37, 31, 14.5, 17.5, -172, -40))
    sc.add('robe', sc.shp([(31, 53), (22, 56.5), (14, 60.5), (9, 66), (7, 80, 1), (72, 80, 1), (70, 67),
                           (65, 61.5), (56, 57.5), (44, 54)]), TE, sh_cloth(3, dark_k=2, light_k=1), line=0)
    band_strand(sc, 'emb_n', [(29.5, 58), (33.5, 64.5), (36.5, 72), (37.5, 81)], 2.0, 'gold',
                sh_rim(3, dark=((1, 0, 1, 1),), light=()), line=0)
    band_strand(sc, 'emb_f', [(49.5, 57), (46.5, 64), (44.5, 72), (44, 81)], 2.0, 'gold',
                sh_rim(3, dark=((1, 0, 1, 1),), light=()), line=0)
    sc.add('book_pages', sc.poly([(41.0, 70.0), (62.0, 65.8), (63.4, 68.6), (42.4, 72.8)]), 'earth',
           sh_rim(4, dark=((0, 1, 1, 1),), light=()), line=0)
    sc.add('book', sc.poly([(42.4, 72.8), (63.4, 68.6), (66.6, 80.5), (45.0, 80.5)]), 'cloth_crimson',
           sh_orb((4, 3, 2, 1), th=(0.5, 0.0, -0.5)), line=0)
    sc.add('book_corner', sc.poly([(60.0, 69.3), (63.4, 68.6), (64.3, 72.0), (61.4, 72.2)]), 'gold',
           sh_flat(3), line=0)
    sc.overlays.append((52.0, 74.0, [".G.", "GyG", ".G."], {'G': PAL['gold'][3], 'y': PAL['gold'][4]}))
    folds(sc, 'robe', [[(15.0, 65.0), (16.0, 72.5), (15.6, 80.0)], [(66.0, 65.0), (65.0, 72.5), (65.4, 80.0)]], 1)
    folds(sc, 'book_pages', [[(43.0, 71.4), (61.8, 67.6)]], 3)
    back = [(24.0, 47.0, 1), (19.0, 40.0), (18.0, 30.0), (20.5, 19.0), (27.5, 11.0), (37.5, 7.5), (48.0, 8.5),
            (55.5, 13.5), (59.5, 22.0), (60.0, 31.0), (58.5, 40.0), (56.5, 46.0, 1), (54.0, 38.0),
            (52.0, 28.0), (42.0, 24.0), (30.0, 32.0), (29.0, 42.0)]
    sc.add('hair_back', sc.shp(back), H, hair_mass_shader(hl), line=0, group='hair')
    add_strands(sc, hl, [
        ('lock_f', [(55, 24), (57, 34), (57.5, 46), (57, 58)], [5, 6, 5, 0]),
        ('bob_k1', [(22, 30), (20, 38), (21.5, 46)], [8, 7, 0]),
    ], H, tip=0.85)
    std_head(sc, face=FACE_FY, neck=NECK_F)
    sc.add('collar', sc.shp([(29, 53.5), (33, 56.4), (39.5, 57.8), (45.5, 55.8), (48.8, 52.6), (49.8, 56.8),
                             (45.5, 60.6), (39, 61.8), (32, 60.6), (28, 57.2)]), TE,
           sh_cloth(3, dark_k=1, light_k=1), line=0)
    band_strand(sc, 'collar_trim', [(28.4, 57.0), (32, 60.4), (39, 61.6), (45.5, 60.4), (49.6, 56.6)], 1.4,
                'gold', sh_flat(3), line=None, outer=None)
    add_strands(sc, hl, [
        ('lock_n', [(28.5, 21), (26.5, 31), (26, 43), (27, 55), (29, 64)], [6, 6.5, 6, 4.5, 0]),
        ('mb6', [(54, 17), (56, 22), (57, 27.5)], [7, 6, 0]),
        ('mb1', [(30.5, 15.5), (29, 21), (28.5, 26.5)], [8, 7, 0]),
        ('mb5', [(49.5, 13.5), (51.5, 19), (52.5, 25)], [8, 7, 0]),
        ('mb2', [(35, 13), (34.5, 19.5), (35, 25.5)], [8, 7.5, 0]),
        ('mb4', [(44.5, 12.5), (45.5, 19), (46.5, 25.5)], [8, 7.5, 0]),
        ('mb3', [(40, 12.5), (40.5, 19), (41, 26.5)], [8, 7.5, 0]),
    ], H, tip=0.8)


# ---------------------------------------------------------------- 角色：薇拉
def build_vera(sc):
    H = 'hair_silver'
    W_ = 'cloth_white'
    SK = 'cloth_sky'
    hl = HairLight(38, 26, 20.5, t1=0.45, t2=0.05, band=arc_band(37, 30, 14.5, 18.0, -172, -40))
    add_strands(sc, hl, [
        ('tail', [(24, 12), (16.5, 15), (12, 23), (11, 34), (12.5, 46), (15.5, 57), (18, 64)],
         [10, 12, 11.5, 10, 8, 5, 0], {'lu': 0.45}),
        ('tail2', [(20, 16), (14.5, 24), (14, 35), (16.5, 46)], [6, 6, 5, 0], {'lu': 0.35}),
    ], H, tip=0.88)
    folds(sc, 'tail', [[(14.0, 20.0), (11.2, 28.0), (10.8, 38.0), (12.0, 48.0)],
                       [(18.0, 26.0), (16.6, 36.0), (17.4, 46.0), (19.0, 54.0)]], 2)
    folds(sc, 'tail', [[(17.2, 16.0), (13.6, 21.0), (12.6, 28.0)], [(13.4, 36.0), (14.2, 44.0)]], 4)
    sc.add('tunic', sc.shp([(31, 53), (21, 56.5), (13, 60.5), (8, 66), (6, 80, 1), (73, 80, 1), (71, 67),
                            (66, 61), (57, 57), (45, 54)]), SK, sh_cloth(3), line=0)
    sc.add('plate', sc.shp([(24, 63), (32, 61), (40, 62.5), (48, 60.8), (56, 62.5), (59, 80, 1), (21, 80, 1)]),
           W_, sh_orb((4, 3, 2, 1), th=(0.45, -0.1, -0.6), w=(0.8, 0.5)), line=0)
    band_strand(sc, 'plate_trim', [(24.3, 62.6), (32, 60.6), (40, 62.1), (48, 60.4), (55.8, 62.1)], 2.0, SK,
                sh_flat(3), line=0)
    ridge(sc, 'plate', 0.0, dark=2, light=4)
    sc.add('gem', sc.ell(40.6, 68.0, 1.8, 2.0), 'magic_blue', sh_orb((4, 3, 2, 1)), line=0)
    for side, pts, trim in [
            ('f', [(50, 55.5), (60, 56.5), (67.5, 60.5), (71.5, 66.5), (70, 72), (63.5, 70.5), (57, 65.5),
                   (51.5, 61)], [(57.2, 65.6), (63.6, 70.8), (70.2, 72.0)]),
            ('n', [(29, 55.5), (18.5, 56.5), (10.5, 60.5), (6.5, 66.5), (8, 72.5), (15, 71), (21.5, 66),
                   (27.5, 61)], [(8.2, 72.4), (15, 71.0), (21.6, 65.9), (27.4, 61.3)])]:
        sc.add('pauld_' + side, sc.shp(pts), W_, sh_orb((4, 3, 2, 1), th=(0.4, -0.1, -0.6)), line=0)
        band_strand(sc, 'ptrim_' + side, trim, 2.0, SK, sh_rim(3, dark=((0, 1, 1, 1),), light=()), line=0)
    back = [(24.5, 42.0, 1), (19.5, 33.0), (19.0, 24.0), (22.5, 15.0), (29.5, 9.5), (38.5, 7.5),
            (47.5, 9.0), (54.5, 14.0), (58.0, 21.0), (58.5, 28.0), (57.0, 33.0, 1), (53.0, 25.0),
            (41.0, 23.0), (29.0, 32.0)]
    sc.add('hair_back', sc.shp(back), H, hair_mass_shader(hl), line=0, group='hair')
    std_head(sc, face=FACE_FM, neck=NECK_F)
    sc.add('collar', sc.shp([(28.5, 53.0), (33, 56.0), (39.5, 57.4), (45.5, 55.4), (49.0, 52.4), (50.0, 56.6),
                             (45.5, 60.4), (39, 61.6), (32, 60.4), (27.6, 57.0)]), SK,
           sh_cloth(3, dark_k=1, light_k=1), line=0)
    band_strand(sc, 'collar_trim', [(28.0, 56.8), (32, 60.2), (39, 61.4), (45.5, 60.2), (49.8, 56.4)], 1.4,
                W_, sh_flat(4), line=None, outer=None)
    add_strands(sc, hl, [
        ('v1', [(52, 14), (55.5, 20), (57, 28), (56.5, 36)], [8, 7, 5, 0]),
        ('v2', [(30, 15), (27.5, 22), (26.5, 30), (27, 38)], [8, 7, 5, 0]),
        ('v6', [(33, 13), (31.5, 18.5), (31.5, 24.5)], [8, 7, 0]),
        ('v3', [(46, 11.5), (50.5, 15.5), (53, 20.5), (54.5, 26)], [9, 8, 5, 0]),
        ('v4', [(41, 11), (44, 16), (46, 21), (47, 27.5)], [9, 8, 5, 0]),
        ('v5', [(36, 11.5), (37.5, 16.5), (39, 21.5), (40, 26.5)], [9, 8, 5, 0]),
    ], H, tip=0.85)
    for i, (pts, ws) in enumerate([([(29.0, 24.5), (24.0, 19.5), (18.5, 16.5)], [3.6, 3.2, 0]),
                                   ([(28.6, 26.0), (22.6, 23.0), (17.0, 22.0)], [3.6, 3.2, 0]),
                                   ([(28.4, 27.6), (23.0, 27.0), (18.5, 28.0)], [3.2, 2.8, 0])]):
        sc.add_strand('wing%d' % i, Strand(pts, ws), 'gold', sh_rim(3, dark=((0, 1, 1, 1),), light=((0, -1, 1, 1),)),
                      line=0, line_same=1, group='wing')
    sc.add('wing_base', sc.ell(29.4, 26.4, 1.9, 2.2), 'cloth_sky', sh_orb((4, 3, 2, 1)), line=0)


# ---------------------------------------------------------------- 角色：艾德里克王
EXTRA.update({
    'hair_greybrown': ['#2e2622', '#4e423a', '#7a6c5c', '#a89a84', '#d4c8b4'],
    'fur_grey': ['#24222a', '#44404a', '#6c6670', '#9a949a', '#c8c2c4'],
    'armor_bluegrey': ['#141c2c', '#26344c', '#46587a', '#7488aa', '#aabcd6'],
    'ivory': ['#4a3e2e', '#7a6a50', '#b4a07c', '#dccaa4', '#f6ecd4'],
    'hair_white': ['#4e4a54', '#807c88', '#b4b0bc', '#dedce4', '#f8f7fb'],
})
EXTRA_PAL.update({k: [hx(c) for c in v] for k, v in EXTRA.items()})


def ermine_spots(sc, name, col):
    """白貂皮上的黑色貂尾斑点（规则错位排布，像真正的貂皮纹）。"""
    p = sc.byname[name]
    m = erode(p.mask, 1)
    spots = np.zeros_like(m)
    ys, xs = np.nonzero(m)
    for y, x in zip(ys, xs):
        if x % 5 == 2 and y % 4 == 1 and ((x // 5) + (y // 4)) % 2 == 0 and y + 1 < sc.h and m[y + 1, x]:
            spots[y, x] = True
            spots[y + 1, x] = True
    p.over = [(spots, col)]


def build_aldric(sc):
    H = 'hair_greybrown'
    CR = 'cloth_crimson'
    hl = HairLight(38, 27, 20.5, t1=0.45, t2=0.05, band=arc_band(37, 31, 14.5, 17.5, -170, -40))
    # 长发（在身后）
    sc.add('hair_long', sc.shp([(24, 22), (18.5, 34), (16.5, 48), (17, 60, 1), (29, 58, 1), (30, 44), (30, 30)]),
           H, hair_mass_shader(hl), line=0, group='hair')
    sc.add('hair_long_f', sc.shp([(54, 24), (59, 34), (61.5, 48), (62.5, 58, 1), (54, 57, 1), (52, 44),
                                  (51, 32)]), H, hair_mass_shader(hl), line=0, group='hair')
    sc.add('robe', sc.shp([(31, 53), (20, 56.5), (12, 60.5), (7, 66), (5, 80, 1), (74, 80, 1), (72, 67),
                           (67, 61), (58, 57), (45, 54)]), CR, sh_cloth(3, dark_k=2, light_k=1), line=0)
    sc.add('ermine', sc.shp([(29, 53), (17, 56.5), (9, 61), (5.5, 67), (8, 72.5), (20, 70), (32, 67.5),
                             (40, 69.5), (48, 67), (60, 69.5), (71.5, 72), (73.5, 66.5), (69, 60.5), (60, 56),
                             (49, 53)]), 'cloth_white', sh_orb((4, 3, 2, 1), th=(0.35, -0.2, -0.65)), line=0)
    ermine_spots(sc, 'ermine', PAL['cloth_black'][2])
    folds(sc, 'robe', [[(20.0, 73.0), (20.6, 80.0)], [(59.0, 73.0), (58.4, 80.0)], [(40.0, 71.0), (40.4, 80.0)]], 2)
    sc.add('hair_back', sc.shp([(25.0, 41.0, 1), (20.0, 32.0), (19.5, 23.0), (23.0, 15.0), (30.0, 10.0),
                                (39.0, 8.5), (48.0, 10.0), (54.5, 14.5), (58.0, 21.5), (58.0, 29.0),
                                (56.0, 34.0, 1), (53.0, 25.0), (41.0, 23.0), (29.0, 31.0)]), H,
           hair_mass_shader(hl), line=0, group='hair')
    std_head(sc, 'skin_old', face=FACE_O, neck=NECK_O)
    beard = [(28.8, 34.0), (30.0, 40.0), (33.0, 44.0), (37.0, 45.6), (41.0, 44.4), (44.8, 43.4), (48.6, 44.2),
             (52.0, 42.6), (55.6, 38.8), (56.8, 45.0), (55.6, 52.0), (53.0, 58.0), (50.0, 63.0), (48.6, 61.0),
             (46.5, 66.5, 1), (44.2, 62.4), (42.0, 66.0, 1), (40.0, 61.0), (37.0, 63.5, 1), (35.5, 57.0),
             (31.5, 51.5), (28.6, 45.5), (27.2, 38.0)]
    sc.add('beard', sc.shp(beard), H, sh_beard(3), line=0, group='beard')
    sc.add('mustache', sc.shp([(39.6, 46.4), (42.0, 43.8), (45.0, 42.8), (48.2, 43.2), (51.0, 45.0),
                               (52.6, 49.0, 1), (49.2, 46.8), (45.5, 46.2), (41.8, 47.2), (38.6, 50.0, 1)]),
           H, sh_beard(3, strokes=False), line=0, group='mustache')
    add_strands(sc, hl, [
        ('al1', [(29, 17), (26.5, 26), (25, 37), (24.5, 48), (26, 58)], [8, 8, 7, 6, 0]),
        ('al2', [(48, 13), (53.5, 18), (56.5, 26), (57.5, 34)], [9, 8, 6, 0]),
        ('al3', [(33, 13), (30.5, 18), (29.5, 24)], [9, 7, 0]),
        ('al4', [(41, 12), (44.5, 16), (47.5, 22)], [10, 8, 0]),
        ('al5', [(36, 12.5), (37, 17), (38.5, 22)], [9, 7, 0]),
    ], H, tip=0.85)
    crown_band = [(24.2, 19.0), (30.0, 16.0), (38.5, 14.6), (47.0, 14.8), (53.6, 16.4), (58.2, 19.2)]
    for nm, pts, ws in [('ant_l', [(39.6, 14.0), (37.2, 10.0), (33.8, 6.6), (30.6, 5.0)], [3.4, 3.2, 2.8, 0]),
                        ('ant_r', [(40.6, 14.0), (43.0, 10.0), (46.4, 6.6), (49.6, 5.0)], [3.4, 3.2, 2.8, 0]),
                        ('ant_l2', [(36.6, 9.8), (35.6, 6.2), (36.2, 3.0)], [3.0, 2.8, 0]),
                        ('ant_r2', [(43.6, 9.8), (44.6, 6.2), (44.0, 3.0)], [3.0, 2.8, 0])]:
        sc.add_strand(nm, Strand(pts, ws), 'cloth_white', sh_rim(4, dark=((1, 1, 1, 1),), light=()), line=0,
                      line_same=None, group='antler')
    for i, (cx, cy, h) in enumerate([(26.6, 18.2, 6.0), (32.4, 15.8, 7.6), (47.8, 15.0, 7.6), (54.2, 16.8, 6.0)]):
        sc.add('cpt%d' % i, sc.poly([(cx - 3.2, cy + 1), (cx, cy - h), (cx + 3.2, cy + 1)]), 'gold',
               sh_rim(3, dark=((1, 0, 1, 1),), light=((-1, 0, 1, 1),)), line=0, group='crown')
    band_strand(sc, 'crown', crown_band, 4.2, 'gold', sh_rim(3, dark=((0, 1, 1, 1),), light=((0, -1, 1, 1),)),
                line=0, group='crown2')
    sc.overlays.append((31.5, 15.5, ["r.......G......r"], {'r': PAL['cloth_crimson'][4], 'G': PAL['magic_blue'][3]}))
    sc.overlays.append((38.5, 58.5, [".dGd.", "dGyGd", ".dGd."], gold_cmap()))


# ---------------------------------------------------------------- 角色：瓦尔德
EYE_V = {s: dict(EYE_O[s]) for s in EYE_O}
EYE_V['near']['normal'] = (["...KKKKK.", ".KKK0000K", "K.WW0H0W.", "..lW012l.", "...llll.."], 0, 1)
EYE_V['near']['smile'] = (["...KKKK..", ".KKKKKKKK", "K.lW0H0l.", "...llll.."], 0, 1)
EYE_V['far']['normal'] = ([".KKKK..", "K0000KK", "W0H0W.K", "lW12l..", ".lll..."], 0, 1)
EYE_V['far']['smile'] = ([".KKKK..", "KKKKKKK", "lW0H0lK", ".llll.."], 0, 1)
MOUTH_V = dict(MOUTH_M)
MOUTH_V.update({
    'normal': [".lll.", "..s.."],
    'smile': ["....l", ".lll.", "..s.."],
    'smile_talk': ["....l", ".lDDl", "..ll."],
})


def build_valder(sc):
    H = 'hair_black'
    CR = 'cloth_crimson'
    IR = 'iron'
    # 披风立领（颈后）
    sc.add('cape', sc.shp([(21, 50), (9, 57), (3, 66), (1.5, 80, 1), (78.5, 80, 1), (77, 66), (71, 57),
                           (59, 50)]), CR, sh_cloth(2, dark_k=2, light_k=1), line=0)
    sc.add('collar_hi', sc.shp([(19.5, 57), (20.5, 44), (24.5, 36.5), (28.5, 44), (30, 55), (48, 55), (51, 43),
                                (57, 35.5), (60.5, 43), (60, 57)]), CR,
           sh_orb((3, 2, 1, 1), th=(0.3, -0.2, -0.7)), line=0)
    sc.add('collar_in', sc.shp([(22.5, 55), (23.5, 45), (25.5, 41.5), (28, 46), (29, 55), (49, 55), (51.5, 46),
                                (56.5, 40), (58.5, 45), (58, 55)]), 'cloth_black', sh_flat(2), line=0)
    sc.add('chest', sc.shp([(23, 58), (57, 57), (60, 80, 1), (20, 80, 1)]), IR,
           sh_orb((4, 3, 2, 1), th=(0.5, 0.0, -0.45), w=(0.8, 0.5)), line=0)
    for side, pts, trim in [
            ('f', [(50, 54.5), (60.5, 55.5), (68.5, 59.5), (73, 66), (71.5, 72.5), (64.5, 71), (57.5, 65.5),
                   (51.5, 60.5)], [(57.6, 65.6), (64.6, 71.2), (71.6, 72.6)]),
            ('n', [(29.5, 54.5), (18.5, 55.5), (10, 59.5), (5.5, 66), (7, 72.5), (14.5, 71), (21.5, 65.5),
                   (28, 60.5)], [(7.2, 72.4), (14.5, 71.0), (21.6, 65.4), (27.8, 60.7)])]:
        sc.add('pauld_' + side, sc.shp(pts), IR, sh_orb((4, 3, 2, 1), th=(0.4, -0.05, -0.55)), line=0)
        band_strand(sc, 'ptrim_' + side, trim, 2.0, 'gold', sh_rim(3, dark=((0, 1, 1, 1),), light=()), line=0)
    ridge(sc, 'chest', 0.0, dark=1, light=3)
    folds(sc, 'cape', [[(4.5, 66.0), (4.0, 80.0)], [(75.5, 66.0), (76.0, 80.0)]], 1)
    sc.add('medal', sc.ell(40.5, 68.5, 5.2, 5.0), 'gold', sh_orb((4, 3, 2, 1)), line=0)
    sc.overlays.append((35.5, 65.5, EAGLE, {'k': PAL['cloth_black'][1]}))
    std_head(sc, face=FACE_G, neck=NECK_O, hollow=HOLLOW_G)
    sc.add('goatee', sc.shp([(42.6, 50.2), (46.8, 49.4), (50.6, 50.8), (49.4, 54.6), (46.8, 59.0, 1),
                             (44.2, 55.0)]), H, sh_beard(3, strokes=False), line=0, group='beard')
    sc.add('mustache', sc.shp([(41.6, 45.4), (44.6, 44.0), (47.8, 44.2), (51.2, 45.8), (52.4, 47.6, 1),
                               (48.2, 45.8), (45.0, 45.8), (42.4, 46.8), (40.6, 48.0, 1)]), H,
           sh_beard(3, strokes=False), line=0, group='mustache')
    hair = [(24.6, 44.0, 1), (20.8, 40.0), (18.0, 42.5, 1), (19.2, 35.0), (16.8, 33.0, 1), (19.4, 27.0),
            (20.0, 21.5), (23.8, 15.4), (30.0, 11.2), (39.0, 9.6), (48.0, 10.6), (54.4, 14.4), (57.6, 20.0),
            (57.2, 25.6, 1), (54.2, 23.4), (50.0, 22.2), (46.8, 22.6), (43.6, 24.4, 1), (40.6, 21.6),
            (36.0, 21.6), (31.6, 23.8), (29.2, 28.2), (28.6, 34.0)]
    hl2 = HairLight(38, 27, 19, base=2, lo=1, hi=4, t1=0.35, t2=-0.1,
                    band=arc_band(38, 31, 16.0, 18.5, -165, -60, teeth=1.5, tw=7))
    p = sc.add('hair', sc.shp(hair), H, hair_mass_shader(hl2, rim=2), line=0, group='hair')
    for pts in ([(54.5, 21.0), (47.0, 15.5), (37.0, 14.0), (28.5, 17.5), (23.0, 25.0), (20.5, 33.0)],
                [(51.0, 22.0), (43.0, 18.2), (34.0, 18.4), (27.4, 23.6), (24.0, 33.0), (22.4, 40.0)],
                [(55.5, 17.5), (48.5, 13.0), (39.0, 11.8), (30.0, 14.0), (24.4, 19.6)],
                [(44.5, 22.5), (38.0, 20.6), (31.0, 21.6)]):
        p.paint.append(stroke(pts, 1))
    p.paint.append(stroke([(33.0, 21.2), (28.2, 25.6), (26.0, 32.0), (25.0, 38.0)], 4))
    p.paint.append(stroke([(31.0, 20.0), (26.6, 23.8), (24.2, 29.0)], 3))
    p.paint.append(stroke([(52.4, 21.0), (46.0, 17.0), (40.0, 16.4)], 3))


# ---------------------------------------------------------------- 角色：戈尔德
FACE_BALD = [
    (27.0, 36.0), (22.4, 34.0), (20.8, 26.0), (22.2, 17.4), (27.6, 11.0), (36.5, 7.6), (46.5, 8.2),
    (53.4, 12.0), (57.0, 18.4), (57.4, 25.0), (56.4, 31.0), (55.8, 35.5), (56.6, 40.0), (56.4, 46.0),
    (54.0, 51.5), (48.5, 55.0, 1), (41.0, 54.0), (34.0, 51.5), (29.8, 47.0),
]


def scalp_hl(sc, p, idx):
    m = p.mask
    hl = sc.ell(33.0, 14.0, 6.0, 3.0) & m
    idx[hl] = 4
    sp = sc.ell(35.5, 16.0, 10.5, 6.5) & m & ~hl
    idx[sp & (idx == 3)] = 3


def build_gord(sc):
    H = 'hair_brown'
    LE = 'leather'
    sc.add('body', sc.shp([(27, 52), (14, 56), (4.5, 62), (1, 70), (0.5, 80, 1), (79.5, 80, 1), (79, 70),
                           (75, 62), (64, 56), (52, 52)]), LE, sh_cloth(3, dark_k=2, light_k=1), line=0)
    folds(sc, 'body', [[(17.0, 62.0), (19.0, 71.0), (19.4, 80.0)], [(63.0, 64.0), (61.0, 72.0), (61.0, 80.0)]], 2)
    sc.add('strap', sc.st(Strand([(58, 54), (46, 64), (33, 74), (24, 81)], [4, 4, 4, 4]))[1], 'cloth_black',
           sh_cloth(2, dark_k=1, light_k=1), line=0)
    for i, (x, y) in enumerate([(52.5, 59.0), (43.0, 66.8), (33.8, 74.2)]):
        sc.add('stud%d' % i, sc.ell(x, y, 1.3, 1.3), 'iron', sh_orb((4, 3, 2, 1)), line=0)
    sc.add('fur', sc.shp([(30, 52.5), (19, 54.5), (9.5, 58.5), (3.5, 63.5), (7, 64.5), (2.5, 68.5, 1), (8, 68),
                          (5.5, 72.5, 1), (11.5, 69.5), (12, 74, 1), (16, 69.5), (19.5, 72.5, 1), (21, 67),
                          (25.5, 68.5, 1), (26.5, 63.5), (31, 63.5, 1), (31.5, 59), (40, 59.5), (48, 57.5),
                          (52.5, 55), (50, 51.5)]), 'hair_brown', sh_beard(3, seed=4), line=0)
    sc.add('pauld', sc.shp([(52, 53.5), (62, 54.5), (70.5, 58.5), (76, 64), (75.5, 71), (68, 69.5), (60, 64),
                            (53.5, 59.5)]), 'iron', sh_orb((4, 3, 2, 1), th=(0.4, -0.05, -0.55)), line=0)
    for i, (x, y) in enumerate([(62.5, 55.5), (69.5, 59.0), (74.0, 64.2)]):
        sc.add('spike%d' % i, sc.poly([(x - 1.8, y + 1.2), (x + 0.5, y - 3.8), (x + 1.8, y + 1.2)]), 'steel',
               sh_rim(3, dark=((1, 0, 1, 1),), light=()), line=0)
    sc.overlays.append((34.5, 71.5, EAGLE, {'k': PAL['cloth_black'][1]}))
    std_head(sc, 'skin_dk', face=FACE_BALD, neck=NECK_B, extra=scalp_hl)
    beard = [(28.2, 35.0), (29.6, 41.0), (32.8, 45.0), (37.0, 46.6), (41.0, 45.4), (44.8, 44.4), (48.6, 45.2),
             (52.2, 43.6), (56.4, 39.0), (58.0, 45.0), (57.4, 52.0), (55.0, 58.0), (51.6, 63.0), (49.0, 61.4),
             (46.4, 66.4, 1), (43.6, 62.0), (40.6, 65.4, 1), (38.4, 60.0), (34.6, 62.6, 1), (33.0, 56.0),
             (29.6, 51.0), (27.0, 44.0), (26.0, 38.0)]
    sc.add('beard', sc.shp(beard), H, sh_beard(3), line=0, group='beard')
    sc.add('mustache', sc.shp([(39.4, 47.0), (42.0, 44.4), (45.2, 43.4), (48.6, 43.8), (51.4, 45.6),
                               (53.0, 49.8, 1), (49.4, 47.4), (45.6, 46.8), (41.8, 47.8), (38.2, 50.6, 1)]),
           H, sh_beard(3, strokes=False), line=0, group='mustache')


EYE_G = {s: dict(EYE_O[s]) for s in EYE_O}
EYE_G['near']['normal'] = (["..KKKKKK.", ".KKKKKKKK", "K.lW0H0l.", "...llll.."], 0, 1)
EYE_G['far']['normal'] = (["KKKKKK.", "KKKKKKK", "lW0H0lK", ".llll.."], 0, 1)
BROW_G = {
    'near': dict(BROW_O['near'], normal=(["BBB......", "BBBBBB...", "..BBBBBBB", "......BBB"], 0, 1)),
    'far': dict(BROW_O['far'], normal=([".....BB", "..BBBBB", "BBBBB..", "BB....."], 0, 1)),
}
MOUTH_G = dict(MOUTH_M)
MOUTH_G.update({
    'normal': ["lllll", ".s.s."],
    'smile': ["l...l", "lTTTl", ".lll."],
    'smile_talk': ["l...l", "lTTTl", "lDDDl", ".lll."],
})


# ---------------------------------------------------------------- 角色：哈根
def build_hagen(sc):
    IR = 'iron'
    ST = 'steel'
    H = 'hair_grey'
    sc.add('body', sc.shp([(26, 52), (13, 56), (4, 62), (1, 70), (0.5, 80, 1), (79.5, 80, 1), (79, 70), (76, 62),
                           (66, 56), (53, 52)]), 'cloth_crimson', sh_cloth(2, dark_k=2, light_k=1), line=0)
    sc.add('chest', sc.shp([(22, 60), (58, 59), (61, 80, 1), (19, 80, 1)]), IR,
           sh_orb((4, 3, 2, 1), th=(0.5, 0.0, -0.45), w=(0.8, 0.5)), line=0)
    ridge(sc, 'chest', 1.0, dark=1, light=3)
    for side, pts, lame in [
            ('f', [(50, 53.5), (62.5, 54.5), (72, 59), (77.5, 65.5), (76.5, 74), (67.5, 72.5), (59.5, 66.5),
                   (52, 60.5)], [(56, 64.2), (63.5, 68.8), (72.5, 70.0), (77.2, 69.4)]),
            ('n', [(29, 53.5), (15.5, 54.5), (6, 59), (1.5, 65.5), (2.5, 74), (11.5, 72.5), (19.5, 66.5),
                   (27.5, 60.5)], [(2.2, 70.2), (10, 69.2), (18.5, 64.0), (25.5, 59.0)])]:
        sc.add('pauld_' + side, sc.shp(pts), ST, sh_orb((4, 3, 2, 1), th=(0.4, -0.05, -0.55)), line=0)
        band_strand(sc, 'lame_' + side, lame, 1.4, 'cloth_crimson', sh_flat(2), line=0)
    sc.add('gorget', sc.shp([(26.5, 51), (32, 55.4), (40.5, 57.2), (48.5, 55), (52.5, 50.5), (54.5, 57.5),
                             (48.5, 62.6), (40, 64), (31.5, 62.6), (25, 58)]), ST,
           sh_orb((4, 3, 2, 1), th=(0.35, -0.15, -0.6), w=(0.9, 0.4)), line=0)
    sc.add('helm_back', sc.shp([(22.0, 46.0, 1), (18.0, 36.0), (17.5, 24.0), (21.0, 14.5), (28.5, 8.0),
                                (38.5, 5.5), (49.0, 7.0), (56.5, 12.0), (60.5, 20.0), (61.0, 30.0),
                                (60.0, 42.0, 1), (55.0, 36.0), (52.0, 24.0), (40.0, 22.0), (30.0, 30.0),
                                (29.0, 46.0)]), IR, sh_orb((4, 3, 2, 1), th=(0.4, -0.05, -0.5)), line=0,
           group='helm')
    sc.byname['helm_back'].paint.append(stroke([(24.0, 13.5), (31.0, 8.2), (40.0, 6.4)], 4))
    std_head(sc, 'skin_old', face=FACE_B, neck=NECK_B, cast=('hair', 'helm3', 'helm2', 'helm4'))
    sc.add('cheek_n', sc.shp([(26.5, 24.5), (31.5, 25.5), (31.8, 36.0), (32.8, 44.5), (30.0, 49.5, 1),
                              (25.0, 45.0), (23.6, 34.0)]), IR, sh_orb((4, 3, 2, 1), th=(0.3, -0.1, -0.6)),
           line=0, group='helm2')
    sc.add('cheek_f', sc.shp([(55.0, 23.5), (58.6, 25.0), (59.4, 34.0), (58.6, 43.0), (56.0, 47.0, 1),
                              (55.4, 38.0), (56.2, 31.0)]), IR, sh_orb((4, 3, 2, 1), th=(0.3, -0.1, -0.6)),
           line=0, group='helm2')
    sc.add('brim', sc.st(Strand([(24.0, 25.0), (31.0, 22.0), (40.0, 20.8), (49.0, 21.2), (55.5, 22.8),
                                 (59.5, 25.0)], [3.6] * 6))[1], ST,
           sh_rim(3, dark=((0, 1, 1, 1),), light=((0, -1, 1, 1),)), line=0, group='helm3')
    sc.add('visor', sc.shp([(27.0, 20.5), (30.0, 12.5), (39.5, 8.4), (50.5, 9.4), (57.5, 14.0), (59.6, 21.0),
                            (49.0, 18.6), (40.0, 18.2), (31.0, 19.8)]), 'steel',
           sh_orb((4, 3, 2, 1), th=(0.35, -0.1, -0.55)), line=0, group='helm4')
    band_strand(sc, 'slit', [(33.0, 15.4), (40.0, 13.5), (48.0, 13.8), (54.0, 16.2)], 1.3, IR, sh_flat(0),
                line=None, outer=None)
    sc.overlays.append((24.5, 38.5, ["h", ".", ".", "h"], {'h': PAL['steel'][4]}))
    sc.overlays.append((57.0, 30.0, ["h", ".", ".", "h"], {'h': PAL['steel'][4]}))
    sc.add('mustache', sc.shp([(38.0, 45.6), (42.0, 43.4), (46.0, 42.8), (50.0, 43.8), (53.5, 43.2),
                               (57.0, 40.0, 1), (56.0, 44.8), (51.4, 47.0), (46.0, 46.4), (42.0, 47.2),
                               (37.4, 48.8), (33.6, 46.4, 1)]), H, sh_beard(4, strokes=False), line=0,
           group='mustache')


# ---------------------------------------------------------------- 角色：摩根
HOLLOW_G = [(49.0, 41.5), (53.8, 40.5), (53.4, 46.0), (50.6, 47.4), (48.6, 45.0)]


BROW_MO = {
    'near': dict(BROW_F['near'], normal=(["BB.......", "..BBB....", ".....BBB."], 0, 0)),
    'far': dict(BROW_F['far'], normal=(["....BB.", "..BB...", "BB....."], 0, 0)),
}


def morgan_sockets(sc, p, idx):
    for cx, cy, rx, ry in [(35.5, 32.6, 6.4, 4.6), (50.8, 32.6, 4.8, 4.4)]:
        m = sc.ell(cx, cy, rx, ry) & p.mask
        idx[m] = np.minimum(idx[m], 2)
    for cx, cy, rx, ry in [(35.4, 36.9, 4.2, 1.3), (50.6, 36.9, 3.0, 1.2), (36.0, 29.4, 4.4, 1.2)]:
        m = sc.ell(cx, cy, rx, ry) & p.mask
        idx[m] = np.minimum(idx[m], 1)


def build_morgan(sc):
    BK = 'cloth_black'
    CR = 'cloth_crimson'
    H = 'hair_black'
    hl = HairLight(38, 27, 20, t1=0.4, t2=0.0)
    sc.add('hood_back', sc.shp([(21, 60), (15.5, 46), (15.5, 30), (20, 17), (29, 8.5), (38, 4.5), (47, 5),
                                (55, 9.5), (61, 17.5), (63.5, 30), (63, 45), (59.5, 58)]), BK,
           sh_orb((4, 3, 2, 1), th=(0.4, -0.1, -0.6)), line=0, group='hood')
    folds(sc, 'hood_back', [[(18.0, 30.0), (17.4, 42.0), (18.6, 54.0)], [(61.0, 28.0), (61.6, 40.0), (60.6, 52.0)]], 1)
    sc.add('robe', sc.shp([(30, 52), (18, 56), (10, 61), (5.5, 68), (4, 80, 1), (75, 80, 1), (73, 68), (68, 61),
                           (60, 56), (48, 52)]), BK, sh_cloth(3, dark_k=2, light_k=1), line=0)
    band_strand(sc, 'trim_n', [(24, 57), (30, 66), (33.5, 81)], 2.4, CR, sh_cloth(3, dark_k=1, light_k=0), line=0)
    band_strand(sc, 'trim_f', [(54, 56), (48.5, 66), (46, 81)], 2.4, CR, sh_cloth(3, dark_k=1, light_k=0), line=0)
    sc.add('amulet', sc.ell(40.0, 70.0, 2.8, 3.4), 'magic_dark', sh_orb((4, 3, 2, 1)), line=0)
    folds(sc, 'robe', [[(14.0, 66.0), (15.0, 73.0), (14.6, 80.0)], [(66.0, 66.0), (65.0, 73.0), (65.4, 80.0)]], 2)
    sc.add('hair_back', sc.shp([(26, 42, 1), (21.5, 32), (22, 20), (28, 12), (38, 9), (48, 10.5), (55, 16),
                                (57.5, 26), (56.5, 34, 1), (53, 24), (41, 22), (30, 31)]), H,
           hair_mass_shader(hl), line=0, group='hair')
    std_head(sc, 'skin_pale', face=FACE_G, neck=NECK_F, hollow=HOLLOW_G, extra=morgan_sockets)
    add_strands(sc, hl, [
        ('mh1', [(31, 16), (29.5, 23), (29.5, 31)], [7, 6, 0]),
        ('mh2', [(37, 14), (37.5, 21), (39.5, 28)], [7, 6, 0]),
        ('mh3', [(45, 14), (47.5, 20), (50, 26.5)], [7, 6, 0]),
        ('mh4', [(51, 16), (54.5, 22), (56, 30)], [6, 5, 0]),
    ], H, tip=0.8)
    sc.add('hood', sc.shp([(22.5, 60.5, 1), (19.5, 47), (19.5, 32), (23, 20), (30, 12), (39, 8.5), (48, 9.5),
                           (55.5, 14), (60, 22), (61.5, 33), (60.5, 46), (57.5, 57, 1), (56.0, 44), (57.0, 32),
                           (54.5, 21.5), (47.5, 16.0), (39.5, 15.0), (32.0, 17.5), (27.0, 25.0), (25.5, 36),
                           (27.0, 50)]), BK, sh_orb((3, 2, 1, 1), th=(0.4, -0.1, -0.6)), line=0, group='hair')
    folds(sc, 'hood', [[(29.0, 12.0), (36.0, 9.6), (44.0, 9.8)], [(22.0, 30.0), (21.6, 42.0), (22.8, 54.0)]], 1)
    band_strand(sc, 'hood_rim', [(26.2, 52.0), (25.2, 38.0), (26.2, 27.0), (31.0, 18.8), (39.5, 16.2),
                                 (47.5, 17.0), (53.6, 22.0), (56.0, 30.0), (55.4, 44.0)], 2.0, CR,
                sh_cloth(3, dark_k=1, light_k=1), line=0, group='hair')


# ---------------------------------------------------------------- 角色：格里姆
def braid(sc, name, pts, width, rmp, bands=()):
    """辫子：一节节的发束（交替明暗），末端扎环。"""
    st = Strand(pts, [width] * (len(pts) - 1) + [width * 0.6])
    p = sc.add_strand(name, st, rmp, None, line=0, group=name)

    def shade(sc_, p_):
        m = p_.mask
        idx = np.full(m.shape, 3, int)
        ys, xs, u, v, N = p_.strand.uv(m)
        seg = (u * 9).astype(int)
        val = np.where(seg % 2 == 0, 3, 2)
        val = np.where(v > 0.3, val - 1, val)
        val = np.where((seg % 2 == 0) & (v < -0.2), 4, val)
        idx[ys, xs] = val
        return np.clip(idx, 1, 4)
    p.shader = shade
    return p


def build_grimm(sc):
    H = 'hair_blonde'
    FUR = 'fur_grey'
    IR = 'iron'
    hl = HairLight(38, 28, 21, t1=0.45, t2=0.05, band=arc_band(37, 32, 15.0, 18.0, -170, -40))
    sc.add('hair_long', sc.shp([(22, 24), (16.5, 36), (14.5, 48), (16, 58, 1), (28, 56, 1), (29.5, 42), (29, 28)]),
           H, hair_mass_shader(hl), line=0, group='hair')
    sc.add('hair_long_f', sc.shp([(55, 24), (60, 34), (62.5, 46), (63, 56, 1), (54, 55, 1), (52, 42), (52, 30)]),
           H, hair_mass_shader(hl), line=0, group='hair')
    sc.add('chest', sc.shp([(22, 58), (58, 57), (61, 80, 1), (19, 80, 1)]), IR,
           sh_orb((4, 3, 2, 1), th=(0.5, 0.0, -0.45), w=(0.8, 0.5)), line=0)
    ridge(sc, 'chest', 0.5, dark=1, light=3)
    band_strand(sc, 'belt', [(19.5, 76), (40, 78.5), (61, 76)], 3.0, 'leather', sh_cloth(3, dark_k=1, light_k=1),
                line=0)
    pelt = [(28, 51.5), (17, 54.5), (8, 58.5), (2.5, 64), (1.5, 70), (5, 69), (3.5, 74.5, 1), (8.5, 71.5),
            (8.5, 77, 1), (13, 72.5), (15, 77.5, 1), (18, 71.5), (21.5, 75, 1), (23, 68.5), (26.5, 70.5, 1),
            (28, 64.5), (33, 62.5), (40, 64.5), (47, 62.5), (52, 64.5), (54, 70.5, 1), (56.5, 68), (59.5, 75, 1),
            (61.5, 71), (65.5, 77.5, 1), (67, 72), (71.5, 76.5, 1), (71.5, 70.5), (76.5, 73.5, 1), (75.5, 67),
            (78.5, 66, 1), (76, 60), (69.5, 55.5), (60, 52.5), (51, 51)]
    sc.add('pelt', sc.shp(pelt), FUR, sh_beard(3, seed=9), line=0)
    sc.add('clasp', sc.ell(40.0, 63.6, 2.6, 2.4), 'gold', sh_orb((4, 3, 2, 1)), line=0)
    std_head(sc, face=FACE_B, neck=NECK_B, cast=('hair', 'helm'))
    beard = [(28.2, 34.0), (29.6, 40.0), (32.8, 44.4), (37.0, 46.2), (41.0, 45.0), (44.8, 44.0), (48.6, 44.8),
             (52.2, 43.2), (56.6, 38.4), (58.0, 45.0), (57.0, 51.5), (54.0, 57.0), (49.0, 60.5), (44.0, 61.0),
             (38.5, 59.5), (33.5, 55.5), (29.6, 50.0), (27.0, 43.0), (26.0, 37.0)]
    sc.add('beard', sc.shp(beard), H, sh_beard(3, seed=2), line=0, group='beard')
    braid(sc, 'braid_n', [(41.0, 57.0), (40.0, 63.0), (39.6, 69.0), (40.0, 72.0)], 3.6, H)
    braid(sc, 'braid_f', [(49.0, 56.5), (50.0, 62.5), (50.6, 68.0), (50.4, 71.0)], 3.4, H)
    sc.add('ring_n', sc.ell(39.8, 68.6, 2.2, 1.2), 'gold', sh_flat(3), line=0)
    sc.add('ring_f', sc.ell(50.6, 67.8, 2.0, 1.2), 'gold', sh_flat(3), line=0)
    sc.add('mustache', sc.shp([(39.0, 46.6), (42.0, 44.2), (45.2, 43.2), (48.6, 43.6), (51.6, 45.4),
                               (53.4, 49.6, 1), (49.6, 47.2), (45.6, 46.6), (41.6, 47.6), (37.6, 50.4, 1)]),
           H, sh_beard(4, strokes=False), line=0, group='mustache')
    add_strands(sc, hl, [
        ('gh1', [(28.5, 20), (26, 28), (25, 36), (25.5, 44)], [7, 7, 6, 0]),
        ('gh2', [(55, 20), (57.5, 27), (58.5, 35)], [6, 6, 0]),
    ], H, tip=0.85)
    for nm, pts, ws, rings in [
            ('horn_n', [(27.0, 16.5), (19.0, 13.5), (13.0, 9.0), (10.6, 4.4), (11.4, 2.0)], [8.0, 6.2, 4.6, 2.4, 0],
             [[(20.0, 10.0), (17.6, 17.0)], [(15.0, 6.0), (12.0, 11.2)]]),
            ('horn_f', [(52.0, 12.5), (59.0, 8.8), (63.8, 4.8), (65.2, 1.8)], [7.4, 5.6, 3.6, 0],
             [[(57.5, 5.6), (60.0, 11.8)], [(61.8, 2.4), (64.8, 6.8)]])]:
        p = sc.add_strand(nm, Strand(pts, ws), 'ivory', sh_rim(3, dark=((1, 1, 1, 1),), light=((-1, -1, 1, 1),)),
                          line=0, group='horn')
        for r in rings:
            p.paint.append(stroke(r, 1))
    sc.add('helm', sc.shp([(23.0, 24.0, 1), (22.0, 16.0), (26.5, 9.5), (34.5, 5.5), (44.0, 5.0), (52.0, 7.8),
                           (57.0, 13.5), (58.4, 21.5, 1), (51.0, 20.2), (41.0, 19.8), (31.0, 21.4)]), IR,
           sh_orb((4, 3, 2, 1), th=(0.45, 0.0, -0.5)), line=0, group='helm')
    sc.byname['helm'].paint.append(stroke([(39.0, 5.6), (40.0, 12.0), (40.2, 19.4)], 4))
    band_strand(sc, 'helm_rim', [(22.8, 23.6), (27.0, 21.4), (34.0, 20.0), (41.0, 19.6), (48.0, 19.8), (54.0, 20.4),
                                 (58.4, 21.6)], 3.0, 'steel', sh_rim(3, dark=((0, 1, 1, 1),), light=((0, -1, 1, 1),)),
                line=0, group='helm')
    sc.overlays.append((27.5, 20.5, ["h.....h.....h.....h"], {'h': PAL['steel'][4]}))


# ---------------------------------------------------------------- 角色：玛莎
def build_martha(sc):
    H = 'hair_white'
    SC = 'cloth_purple'
    hl = HairLight(38, 27, 20, base=3, lo=1, hi=4, t1=0.4, t2=-0.05,
                   band=arc_band(38, 30, 14.0, 17.0, -150, -60, teeth=1.5, tw=7))
    sc.add('scarf_tail', sc.shp([(22.5, 27.0), (15.0, 33.5), (12.5, 42.0, 1), (18.0, 38.5), (17.5, 45.5, 1),
                                 (23.0, 37.5), (26.0, 31.5)]), SC, sh_cloth(3, dark_k=2, light_k=1), line=0)
    sc.add('dress', sc.shp([(31, 53), (21, 56.5), (13, 60.5), (8, 66), (6, 80, 1), (73, 80, 1), (71, 67),
                            (66, 61), (57, 57), (45, 54)]), 'cloth_brown', sh_cloth(3), line=0)
    sc.add('shawl', sc.shp([(28, 54.5), (17, 57.5), (9.5, 62), (6.5, 69), (9, 76), (18, 74), (29, 70), (37, 72.5),
                            (43.5, 74, 1), (45.5, 68), (52, 69), (62, 73), (70, 74.5), (72.5, 67), (68.5, 61),
                            (60, 57), (50, 54.5)]), 'cloth_olive', sh_orb((4, 3, 2, 1), th=(0.4, -0.15, -0.6)),
           line=0)
    sc.byname['shawl'].paint.append(stroke([(20.0, 62.0), (29.0, 66.5), (38.5, 70.5)], 2))
    sc.byname['shawl'].paint.append(stroke([(58.0, 61.0), (52.0, 64.5), (46.5, 68.5)], 2))
    sc.add('knot', sc.ell(42.8, 71.0, 3.2, 2.8), 'cloth_olive', sh_orb((4, 3, 2, 1)), line=0)
    folds(sc, 'dress', [[(24.0, 76.0), (23.4, 80.0)], [(56.0, 76.0), (56.6, 80.0)]], 2)
    sc.add('hair_back', sc.shp([(25.0, 40.0, 1), (20.0, 32.0), (20.0, 23.0), (24.0, 15.0), (30.5, 10.0),
                                (39.0, 8.5), (48.0, 10.0), (54.5, 14.5), (57.5, 21.0), (57.5, 28.0),
                                (56.0, 32.0, 1), (53.0, 25.0), (41.0, 22.5), (29.0, 30.0)]), H,
           hair_mass_shader(hl), line=0, group='hair')
    std_head(sc, 'skin_old', face=FACE_F, neck=NECK_F)
    hair_f = [(26.2, 38.0, 1), (24.6, 30.0), (25.6, 22.0), (30.0, 15.4), (38.0, 11.6), (47.0, 11.8), (53.6, 15.0),
              (57.2, 21.0), (57.6, 28.5, 1), (54.6, 24.8), (50.6, 23.0), (46.0, 22.8), (42.0, 21.6),
              (37.0, 22.4), (32.6, 24.6), (29.6, 28.6), (28.4, 34.0)]
    p = sc.add('hair_front', sc.shp(hair_f), H, hair_mass_shader(hl, rim=1), line=0, group='hair')
    for pts, i in (([(55.5, 21.5), (50.0, 17.6), (43.0, 15.8), (36.0, 16.8), (30.0, 20.6), (27.0, 26.0)], 2),
                   ([(51.5, 23.0), (45.0, 19.8), (38.0, 19.8), (32.0, 22.4), (28.6, 27.2), (27.4, 33.0)], 2),
                   ([(53.0, 16.4), (46.0, 14.0), (38.0, 14.6), (31.0, 18.0)], 4),
                   ([(56.2, 25.0), (53.5, 22.0)], 1)):
        p.paint.append(stroke(pts, i))
    sc.add('bun', sc.ell(22.8, 18.5, 5.6, 5.4), H, hair_mass_shader(hl), line=0, group='hair')
    sc.byname['bun'].paint.append(stroke([(19.0, 15.5), (22.5, 18.5), (26.5, 21.0)], 2))
    sc.byname['bun'].paint.append(stroke([(20.0, 19.5), (23.0, 22.0)], 2))
    scarf = [(21.8, 28.5, 1), (18.5, 21.5), (19.8, 14.0), (25.5, 8.4), (33.5, 5.4), (41.5, 5.2), (46.4, 7.0),
             (43.0, 9.6), (37.0, 11.8), (31.0, 15.6), (27.0, 20.6), (25.0, 26.6)]
    p = sc.add('scarf', sc.shp(scarf), SC, sh_orb((4, 3, 2, 1), th=(0.4, -0.1, -0.6)), line=0, group='hair')
    p.paint.append(stroke([(24.0, 12.0), (28.5, 12.5), (33.0, 9.0)], 2))
    sc.overlays.append((27.0, 8.5, ["..y...", "......", "y...y.", ".....y"], {'y': PAL['gold'][4]}))


# ---------------------------------------------------------------- 角色：奥斯温
def build_oswin(sc):
    H = 'hair_brown'
    AR = 'armor_bluegrey'
    NV = 'cloth_navy'
    hl = HairLight(38, 26, 20.5, t1=0.45, t2=0.05, band=arc_band(37, 30, 15.0, 18.0, -170, -45))
    sc.add('cape', sc.shp([(22, 55), (9, 61), (3.5, 69), (2, 80, 1), (78, 80, 1), (76.5, 69), (71, 61), (58, 55)]),
           NV, sh_cloth(2, dark_k=2, light_k=1), line=0)
    sc.add('chest', sc.shp([(22, 60), (57, 59), (61, 80, 1), (19, 80, 1)]), AR,
           sh_orb((4, 3, 2, 1), th=(0.5, 0.0, -0.45), w=(0.8, 0.5)), line=0)
    folds(sc, 'cape', [[(5.0, 70.0), (4.6, 80.0)], [(75.0, 70.0), (75.4, 80.0)]], 1)
    sc.add('crest', sc.shp([(36.0, 65.0, 1), (44.0, 65.0, 1), (44.0, 70.5), (40.0, 74.5, 1), (36.0, 70.5)]),
           'cloth_navy', sh_flat(3), line=0)
    sc.overlays.append((37.5, 66.5, ["G.G.G", ".GGG.", "..G..", ".G.G."], {'G': PAL['gold'][3]}))
    for side, pts, trim in [
            ('f', [(49.5, 55.5), (60, 56.5), (68, 60.5), (72.5, 67), (71, 73), (64, 71.5), (57, 66), (51, 61.5)],
             [(57.5, 66.2), (64.2, 71.6), (71.2, 73.0)]),
            ('n', [(29.5, 55.5), (18, 56.5), (9.5, 60.5), (5, 67), (6.5, 73.5), (14, 72), (21, 66.5), (28, 61.5)],
             [(6.8, 73.4), (14, 72.0), (21.2, 66.4), (27.8, 61.8)])]:
        sc.add('pauld_' + side, sc.shp(pts), AR, sh_orb((4, 3, 2, 1), th=(0.45, 0.0, -0.5)), line=0)
        band_strand(sc, 'ptrim_' + side, trim, 2.0, 'gold', sh_rim(3, dark=((0, 1, 1, 1),), light=()), line=0)
    sc.add('gorget', sc.shp([(28.5, 52), (33, 55.2), (40, 56.6), (46.5, 54.6), (49.5, 51.5), (51.5, 57),
                             (46.5, 61.2), (39, 62.4), (32, 61), (27, 57.5)]), AR,
           sh_orb((4, 3, 2, 1), th=(0.4, -0.1, -0.6), w=(0.9, 0.4)), line=0)
    sc.add('hair_back', sc.shp([(25.0, 41.0, 1), (20.0, 33.0), (19.5, 24.0), (23.0, 15.5), (30.0, 10.5),
                                (39.0, 9.0), (48.0, 10.5), (54.5, 15.0), (57.5, 21.5), (57.5, 28.0),
                                (56.0, 31.0, 1), (53.0, 24.0), (41.0, 22.5), (29.5, 30.0)]), H,
           hair_mass_shader(hl), line=0, group='hair')
    std_head(sc, face=FACE_O, neck=NECK_O)
    beard = [(28.6, 35.0), (30.0, 41.0), (33.0, 45.6), (37.0, 47.4), (41.0, 46.6), (44.8, 46.0), (48.6, 46.6),
             (52.0, 45.0), (55.4, 40.4), (55.6, 45.5), (53.4, 50.4), (49.5, 54.6), (47.0, 55.6, 1), (44.0, 55.0),
             (39.5, 53.0), (34.0, 49.6), (30.0, 45.0), (27.6, 39.0)]
    sc.add('beard', sc.shp(beard), H, sh_beard(2, strokes=False), line=0, group='beard')
    sc.add('mustache', sc.shp([(41.0, 45.6), (44.0, 44.0), (47.4, 44.2), (50.6, 45.6), (51.6, 47.4, 1),
                               (47.8, 46.4), (44.6, 46.4), (41.8, 47.2), (39.8, 48.2, 1)]), H,
           sh_beard(2, strokes=False), line=0, group='mustache')
    add_strands(sc, hl, [
        ('o1', [(30, 15), (27.8, 21), (27.2, 28)], [9, 7, 0]),
        ('o4', [(46, 11.5), (51.5, 14.5), (55.5, 20.5)], [9, 7, 0]),
        ('o2', [(34, 12), (36.5, 16.5), (40, 21)], [10, 8, 0]),
        ('o3', [(39, 11), (44, 14.5), (48.5, 20.5)], [10, 8, 0]),
    ], H, tip=0.85)


# ---------------------------------------------------------------- 角色：本笃院长
def build_abbot(sc):
    H = 'cloth_white'
    BR = 'cloth_brown'
    hl = HairLight(38, 27, 20, base=3, lo=1, hi=4, t1=0.45, t2=0.0)
    sc.add('robe', sc.shp([(30, 52), (19, 56), (11, 60.5), (6.5, 67), (5, 80, 1), (74, 80, 1), (72, 67), (67, 60.5),
                           (59, 56), (48, 52)]), BR, sh_cloth(3, dark_k=2, light_k=1), line=0)
    sc.add('hood', sc.shp([(24.5, 53.5), (21.5, 48), (26.5, 45.5), (34, 47.5), (45, 47.5), (52.5, 45.5), (57, 48.5),
                           (56, 55.5), (49, 58.5), (40, 59.5), (31, 58.5)]), BR,
           sh_orb((4, 3, 2, 1), th=(0.4, -0.1, -0.6)), line=0)
    folds(sc, 'robe', [[(16.0, 64.0), (17.0, 72.0), (16.6, 80.0)], [(64.0, 64.0), (63.0, 72.0), (63.4, 80.0)],
                       [(28.0, 66.0), (27.0, 80.0)], [(52.0, 66.0), (53.0, 80.0)]], 2)
    band_strand(sc, 'cord', [(33.5, 58.5), (36.5, 64.0), (39.5, 67.6)], 1.4, 'earth', sh_flat(3), line=None,
                outer=None)
    band_strand(sc, 'cord2', [(47.0, 58.0), (44.0, 63.5), (41.0, 67.4)], 1.4, 'earth', sh_flat(3), line=None,
                outer=None)
    sc.add('stag', sc.shp([(38.0, 67.0), (43.0, 67.0), (43.4, 71.5), (40.6, 74.0, 1), (37.8, 71.5)]), 'wood',
           sh_orb((4, 3, 2, 1)), line=0)
    sc.add('fringe', sc.shp([(26.5, 42.0, 1), (21.5, 37.5), (20.6, 30.0), (22.6, 24.6), (26.0, 29.0), (28.6, 35.0)]),
           H, hair_mass_shader(hl), line=0, group='hair')
    std_head(sc, 'skin_old', face=FACE_BALD, neck=NECK_O, extra=scalp_hl, cast=('hairx',))
    sc.add('fringe_f', sc.shp([(55.6, 24.0), (57.8, 26.0), (57.2, 31.5, 1), (55.6, 28.4)]), H,
           hair_mass_shader(hl), line=0, group='hair')
    beard = [(28.8, 36.0), (30.2, 41.5), (33.2, 45.4), (37.2, 47.0), (41.0, 46.0), (44.8, 45.2), (48.6, 46.0),
             (52.0, 44.2), (55.4, 40.6), (56.6, 46.0), (55.0, 52.5), (52.0, 58.0), (49.0, 62.0), (46.6, 60.4),
             (44.6, 64.4, 1), (42.2, 60.4), (39.6, 62.8, 1), (38.0, 57.0), (33.4, 52.4), (29.6, 47.0), (27.8, 40.0)]
    sc.add('beard', sc.shp(beard), H, sh_beard(3, seed=6), line=0, group='beard')
    sc.add('mustache', sc.shp([(39.8, 47.2), (42.2, 45.0), (45.2, 44.2), (48.4, 44.6), (51.2, 46.2),
                               (52.8, 50.0, 1), (49.4, 47.8), (45.6, 47.2), (41.8, 48.2), (38.8, 50.8, 1)]),
           H, sh_beard(4, strokes=False), line=0, group='mustache')


# ---------------------------------------------------------------- 通用：黑鹰士兵 / 村民
def mail_speckle(sc, p, idx):
    ys, xs = np.nonzero(p.mask)
    for y, x in zip(ys, xs):
        if (x + (y % 2)) % 2 == 0:
            idx[y, x] = max(1, idx[y, x] - 1)


def build_soldier(sc):
    IR = 'iron'
    LE = 'leather'
    sc.add('body', sc.shp([(27, 53), (16, 57), (8, 61.5), (3.5, 68), (2.5, 80, 1), (77.5, 80, 1), (76.5, 68),
                           (72, 61.5), (64, 57), (53, 53)]), LE, sh_cloth(3, dark_k=2, light_k=1), line=0)
    sc.add('tabard', sc.shp([(25, 60), (55, 59), (58, 80, 1), (22, 80, 1)]), 'cloth_black',
           sh_cloth(3, dark_k=2, light_k=1), line=0)
    sc.overlays.append((35, 66, EAGLE, {'k': PAL['cloth_crimson'][3]}))
    folds(sc, 'tabard', [[(29.5, 66.0), (28.6, 73.0), (28.4, 80.0)], [(51.0, 66.0), (52.0, 73.0), (52.4, 80.0)]], 1)
    for side, pts in [('f', [(50.5, 54.5), (61, 55.5), (69, 59.5), (73.5, 66), (72, 72), (65, 70.5), (58, 65),
                             (52, 60.5)]),
                      ('n', [(29.5, 54.5), (18.5, 55.5), (10, 59.5), (5.5, 66), (7, 72), (14, 70.5), (21, 65),
                             (28, 60.5)])]:
        sc.add('pauld_' + side, sc.shp(pts), IR, sh_orb((4, 3, 2, 1), th=(0.45, 0.0, -0.5)), line=0)
    sc.add('coif', sc.shp([(26.5, 49.0), (29.5, 44.0), (34.0, 49.0), (40.0, 52.0), (47.0, 51.0), (52.0, 46.0),
                           (55.5, 48.5), (55.5, 55.5), (49.0, 60.5), (40.0, 61.8), (31.5, 60.5), (25.5, 56.0)]),
           'steel', sh_orb((3, 2, 2, 1), th=(0.4, -0.1, -0.6)), line=0)
    sc.byname['coif'].paint.append(mail_speckle)
    std_head(sc, face=FACE_M, neck=NECK_M, cast=('hair', 'helm'))
    sc.add('helm', sc.shp([(23.5, 30.0, 1), (22.0, 20.0), (26.0, 12.0), (34.0, 7.0), (44.0, 6.4), (52.5, 9.4),
                           (57.5, 16.0), (59.0, 25.0, 1), (51.0, 24.0), (41.0, 23.6), (31.0, 25.0), (26.5, 29.0)]),
           IR, sh_orb((4, 3, 2, 1), th=(0.45, 0.0, -0.5)), line=0, group='helm')
    sc.byname['helm'].paint.append(stroke([(40.0, 7.0), (41.0, 14.0), (41.2, 22.4)], 4))
    band_strand(sc, 'brim', [(20.0, 29.0), (26.0, 26.0), (34.0, 24.2), (42.0, 23.8), (50.0, 24.2), (57.0, 25.6),
                             (62.0, 28.0)], 3.2, IR, sh_rim(3, dark=((0, 1, 1, 1),), light=((0, -1, 1, 1),)), line=0,
                group='helm')
    sc.overlays.append((37.5, 14.5, ["r.....r", "rr.r.rr", ".rrrrr.", "..rrr..", ".r.r.r."],
                        {'r': PAL['cloth_crimson'][3]}))


def build_villager(sc):
    H = 'hair_brown'
    hl = HairLight(38, 26, 21, t1=0.5, t2=0.12, band=arc_band(37, 30, 15.5, 18.5, -170, -45, teeth=2.0, tw=8))
    sc.add('tunic', sc.shp([(30, 53), (20, 57), (12, 61), (7, 67), (5, 80, 1), (74, 80, 1), (73, 68), (67, 62),
                            (57, 57.5), (45, 54)]), 'cloth_olive', sh_cloth(3), line=0)
    sc.byname['tunic'].paint.append(stroke([(16.0, 64.0), (19.0, 72.0), (20.0, 80.0)], 2))
    sc.byname['tunic'].paint.append(stroke([(62.0, 63.0), (60.0, 71.0), (60.5, 80.0)], 2))
    sc.add('shirt_v', sc.poly([(33.0, 57.0), (46.0, 56.0), (40.5, 67.0)]), 'earth', sh_cloth(4, dark_k=1, light_k=0),
           line=0)
    sc.overlays.append((38.5, 59.0, ["l.l", ".l.", "l.l", ".l."], {'l': PAL['leather'][1]}))
    back = [(24.0, 44.0, 1), (19.0, 35.0), (18.5, 25.0), (22.0, 15.5), (29.0, 9.0), (38.5, 6.5), (48.0, 7.5),
            (55.5, 12.0), (59.5, 19.0), (60.0, 26.0), (58.0, 32.0, 1), (54.0, 26.0), (42.0, 24.0), (30.0, 34.0)]
    sc.add('hair_back', sc.shp(back), H, hair_mass_shader(hl), line=0, group='hair')
    add_strands(sc, hl, [
        ('k1', [(23.5, 26), (18.5, 33), (16, 39)], [10, 7, 0]),
        ('k2', [(26, 32), (22.5, 39), (21.5, 45)], [9, 6, 0]),
    ], H, tip=0.8)
    std_head(sc, face=FACE_M, neck=NECK_M)
    sc.add('kerchief', sc.shp([(27.0, 53.0), (32.0, 56.0), (39.5, 57.8), (46.5, 56.0), (50.5, 52.6), (52.0, 57.0),
                               (46.5, 61.5), (41.5, 66.5, 1), (37.5, 61.5), (30.5, 60.0), (26.0, 56.8)]),
           'cloth_crimson', sh_orb((4, 3, 2, 1), th=(0.4, -0.1, -0.6)), line=0)
    add_strands(sc, hl, [
        ('t2', [(33, 13), (27.5, 8.5), (22.5, 8)], [10, 7, 0]),
        ('t1', [(40, 12), (44, 7), (50, 5)], [9, 6, 0]),
        ('b5', [(48, 11), (53, 15.5), (57, 20), (59.5, 25)], [10, 8, 5, 0]),
        ('b1', [(29, 15), (27, 22.5), (26.5, 29.5), (27.5, 34.5)], [9, 7, 4, 0]),
        ('b4', [(44, 10), (46.5, 16), (49, 21), (51, 26)], [10, 8, 5, 0]),
        ('b2', [(33.5, 11), (32.5, 17.5), (33.5, 22.5), (35.5, 26)], [10, 9, 6, 0]),
        ('b3', [(38.5, 10.5), (39.5, 16.5), (41.5, 21.5), (43.5, 26.5)], [10, 9, 6, 0]),
    ], H, tip=0.8)


# 皱纹（贴在脸上、五官之前；被胡子/头发盖住的部分自动不画）
WRINKLES = {
    'old': [(28, 32, ["S.", "..", "S.", ".S"]),          # 鱼尾纹
            (33, 38, [".sss."]), (48, 38, ["ss."]),         # 眼袋
            (45, 41, ["S", "S", ".", "."]), (44, 43, ["S"]),  # 法令纹
            (51, 41, ["s", ".s"]),
            (36, 23, ["SSS...SS"]), (38, 25, ["ss..ss"])],  # 抬头纹
    'mid': [(28, 33, ["S", ".", "S"]), (45, 41, ["s", "s"]), (51, 41, ["s"])],
}

FULL = ['normal', 'smile', 'angry', 'sad', 'surprise']
MID = ['normal', 'smile', 'angry']
ONE = ['normal']

# 五官默认锚点（同一套头部比例，所有人一致）
ANCHORS = dict(eye_n=(31, 31), eye_f=(47, 31), brow_n=(30, 27), brow_f=(47, 27), nose=(47, 38), mouth=(43, 44))


def char(build, skin, eye, hair, eyes='M', brows=None, mouths=None, exprs=FULL, brow_col=(1, 0), **kw):
    d = dict(ANCHORS)
    d.update(build=build, skin=skin, eye=eye, hair=hair, eyes=eyes, brows=brows or eyes,
             mouths=mouths or eyes, exprs=exprs, brow_col=brow_col)
    d.update(kw)
    return d


FRECKLES = [(34, 38, ["s.s", "...", ".s."]), (50, 38, ["s.", ".s"]), (44, 37, ["s"])]

CHARS = {
    'elwin': char(build_elwin, 'skin', 'eye_blue', 'hair_ash', 'M',
                  marks=[(52, 26, ["S.", ".S"])]),
    'nora': char(build_nora, 'skin', 'eye_green', 'hair_brown', 'F', marks=FRECKLES),
    'serin': char(build_serin, 'skin', 'eye_violet', 'hair_black', 'F', brow_col=(2, 1)),
    'doran': char(build_doran, 'skin', 'eye_brown', 'hair_brown', 'O', mouths='M',
                  marks_top=[(40, 35, ["..hh...", "SSSSSS.", ".hhh..."])]),
    'sid': char(build_sid, 'skin', 'eye_amber', 'hair_red', 'M', mouths='S', brows='S'),
    'mira': char(build_mira, 'skin', 'eye_gold', 'hair_lav', 'F', post=mira_glasses, brow_col=(1, 0)),
    'vera': char(build_vera, 'skin', 'eye_ice', 'hair_silver', 'F2', brows='F', mouths='F', brow_col=(2, 1)),
    'aldric': char(build_aldric, 'skin_old', 'eye_brown', 'hair_greybrown', 'T', mouths='M', mouth_on=('beard',),
                   mouth=(43, 47), wr='old', mini_c=(40.5, 31.0)),
    'valder': char(build_valder, 'skin', 'eye_grey', 'hair_black', 'V', brows='O', mouths='V', wr='mid',
                   mouth=(43, 47), mouth_on=('goatee',),
                   marks_top=[(50, 38, ["h...", "lh..", ".lh.", "..lh", "...l"])]),
    'gord': char(build_gord, 'skin_dk', 'eye_brown', 'hair_brown', 'G', brows='G', mouths='G', exprs=MID,
                 mouth_on=('beard',), mouth=(43, 48), marks_top=[(33, 25, ["h...", ".S..", ".hS.", "..hS", "...h"])]),
    'hagen': char(build_hagen, 'skin_old', 'eye_brown', 'hair_grey', 'O', mouths='V', exprs=MID, mouth=(43, 48),
                  wr='old'),
    'morgan': char(build_morgan, 'skin_pale', 'eye_red', 'hair_black', 'V', brows='MO', mouths='V', exprs=MID,
                   marks_top=[(52, 41, ["S", "S", ".S"]), (30, 40, ["S", ".S"])]),
    'grimm': char(build_grimm, 'skin', 'eye_blue', 'hair_blonde', 'O', mouths='G', exprs=MID, mouth_on=('beard',),
                  mouth=(43, 47), brow_col=(1, 0), wr='mid', mini_s=0.62, mini_c=(39.5, 30.0)),
    'martha': char(build_martha, 'skin_old', 'eye_brown', 'cloth_white', 'O', brows='F', mouths='F', exprs=MID,
                   brow_col=(1, 0), wr='old', marks=[(42, 46, ["S", "S"]), (49, 46, ["s"])]),
    'oswin': char(build_oswin, 'skin', 'eye_blue', 'hair_brown', 'O', mouths='M', exprs=MID, mouth_on=('beard',),
                  mouth=(43, 47), wr='mid'),
    'abbot': char(build_abbot, 'skin_old', 'eye_grey', 'cloth_white', 'O', mouths='M', exprs=MID,
                  mouth_on=('beard',), mouth=(43, 48), brow_col=(2, 1), wr='old'),
    'soldier': char(build_soldier, 'skin', 'eye_brown', 'hair_brown', 'O', mouths='M', exprs=ONE),
    'villager': char(build_villager, 'skin_dk', 'eye_brown', 'hair_brown', 'M', exprs=ONE),
    'glenn': char(build_glenn, 'skin_old', 'eye_grey', 'hair_grey', 'O', mouths='M', mouth_on=('beard',),
                  brow_col=(1, 0), mouth=(43, 46), wr='old'),
}

EYE_F2 = {
    'near': dict(EYE_F['near'],
                 normal=(["...KKKKK..", ".KKK0000K.", "KK.W0H001.", "K.W00H112.", "..KW01233.", "....lll..."], 0, -1),
                 smile=(["...KKKKK..", ".KKK0000K.", "KK.W0H001.", "K.lW0H11l.", "....llll.."], 0, -1),
                 angry=(["..KK......", ".KKKKKK...", "KK.W0KKKK.", "K.W00H1KK.", "..KW01233.", "....lll..."], 0, -1),
                 sad=(["......KK..", "...KKK00K.", "KKKKW0H01.", "K.W00H112.", "..KW01233.", "....lll..."], 0, -1),
                 surprise=(["...KKKKK..", ".KKKwwwwK.", "KK.W1000W.", "K.W00H01W.", "..W01123W.", "..KWW33W..",
                            "....lll..."], 0, -2)),
    'far': dict(EYE_F['far'],
                normal=(["..KKKK..", ".K0000KK", "KWH001.K", ".W0H12..", ".W1233K.", "..lll..."], 0, -1),
                smile=(["..KKKK..", ".K0000KK", "KWH001.K", ".l0H12l.", "..llll.."], 0, -1),
                angry=([".....KK.", "...KKKKK", "KKKK01.K", ".W0H12..", ".W1233K.", "..lll..."], 0, -1),
                sad=([".KK.....", ".K0KKK..", "KWH00KKK", ".W0H12.K", ".W1233K.", "..lll..."], 0, -1),
                surprise=(["..KKKK..", ".KwwwwKK", "KW1000WK", ".W0H01W.", ".W0123W.", ".WW33WK.",
                           "..lll..."], 0, -2)),
}
EYE_T = {s: dict(EYE_O[s]) for s in EYE_O}
EYE_T['near']['normal'] = (["...KKKK..", ".KKKKKKKK", "K.W0H01W.", "..lW123l.", "...lll..."], 0, 1)
EYE_T['far']['normal'] = ([".KKKK..", "KKKKKKK", "WH01W.K", "lW12l..", ".ll...."], 0, 1)
BROW_T = {
    'near': dict(BROW_O['near'], normal=(["......BB.", "..BBBBB.B", "BBB......"], 0, 1)),
    'far': dict(BROW_O['far'], normal=(["BB.....", "B.BBBB.", "......B"], 0, 1)),
}
EYES = {'M': EYE_M, 'F': EYE_F, 'O': EYE_O, 'V': EYE_V, 'G': EYE_G, 'F2': EYE_F2, 'T': EYE_T}
BROW_S = {'near': BROW_M['near'],
          'far': dict(BROW_M['far'], normal=([".BBBB..", "B....B."], 0, -1))}
BROWS = {'M': BROW_M, 'F': BROW_F, 'O': BROW_O, 'S': BROW_S, 'G': BROW_G, 'MO': BROW_MO, 'T': BROW_T}
MOUTHS = {'M': MOUTH_M, 'F': MOUTH_F, 'S': MOUTH_S, 'V': MOUTH_V, 'G': MOUTH_G}


_SCENES = {}


def get_scene(cid):
    if cid not in _SCENES:
        sc = Scene()
        CHARS[cid]['build'](sc)
        sc.render()
        _SCENES[cid] = sc
    return _SCENES[cid]


def render_frame(cid, expr='normal', frame=''):
    spec = CHARS[cid]
    sc = get_scene(cid)
    rgba = sc.rgba.copy()
    on = sc.ids('face', *spec.get('feat_on', ()))
    hair_ids = {i for i, p in enumerate(sc.parts) if p.group == 'hair'}
    cm = feature_cmap(spec['skin'], spec['eye'], spec.get('brow_ramp', spec['hair']), spec['brow_col'])
    eyes, brows, mouths = EYES[spec['eyes']], BROWS[spec['brows']], MOUTHS[spec['mouths']]
    ek = ('blink_' + expr) if frame == 'blink' else expr
    if frame == 'blink' and ek not in eyes['near']:
        ek = 'blink'
    for mx, my, rows in WRINKLES.get(spec.get('wr'), []) + list(spec.get('marks', ())):
        stamp(rgba, sc.owner, on, mx, my, (rows, 0, 0), cm)
    stamp(rgba, sc.owner, on, *spec['eye_n'], tget(eyes['near'], ek), cm)
    stamp(rgba, sc.owner, on, *spec['eye_f'], tget(eyes['far'], ek), cm)
    ball = on | (hair_ids if spec.get('brow_over') else set())
    stamp(rgba, sc.owner, ball, *spec['brow_n'], tget(brows['near'], expr), cm)
    stamp(rgba, sc.owner, ball, *spec['brow_f'], tget(brows['far'], expr), cm)
    mk = expr + ('_talk' if frame == 'talk' else '')
    mon = sc.ids('face', *spec.get('mouth_on', ()))
    stamp(rgba, sc.owner, mon, *spec['mouth'], tget(mouths, mk), cm)
    stamp(rgba, sc.owner, on, *spec['nose'], (spec.get('nose_t', NOSE_M), 0, 0), cm)
    for mx, my, rows in spec.get('marks_top', ()):
        stamp(rgba, sc.owner, on, mx, my, (rows, 0, 0), cm)
    if spec.get('post'):
        spec['post'](sc, rgba, expr, frame)
    return rgba


# ---------------------------------------------------------------- 预览
def to_img(rgba):
    return Image.fromarray(rgba, 'RGBA')


def contact(imgs, cols, scale=3, bg=(52, 50, 66, 255), pad=2):
    w, h = imgs[0].size
    rows = (len(imgs) + cols - 1) // cols
    out = Image.new('RGBA', (cols * (w + pad) + pad, rows * (h + pad) + pad), bg)
    for i, im in enumerate(imgs):
        x = pad + (i % cols) * (w + pad)
        y = pad + (i // cols) * (h + pad)
        out.alpha_composite(im, (x, y))
    return out.resize((out.width * scale, out.height * scale), Image.NEAREST)


ORDER = ['elwin', 'glenn', 'nora', 'serin', 'doran', 'sid', 'mira', 'vera', 'aldric', 'valder',
         'gord', 'hagen', 'morgan', 'grimm', 'martha', 'oswin', 'abbot', 'soldier', 'villager']
FRAME_KINDS = ('', 'talk', 'blink')
SHEET_COLS = 15


def frame_name(cid, expr, fr):
    return '%s_%s' % (cid, expr) + ('_' + fr if fr else '')


MINI_S = 0.68                 # 小头像缩放：同一套矢量形状按 0.68 倍重绘（整头入画，五官用小模板）
MINI_C = (40.5, 33.5, 16.0, 16.8)
MINI_FEAT = {
    'M': dict(en=["..KKKK", ".KKK0K", "K.W0H.", "...12."], ef=[".KKK.", "KK0KK", "W0H.K", ".12.."],
              bn=[".BBBB", "B...."], bf=["BBBB.", "....B"], mo=[".ll"], dy=0.0),
    'F': dict(en=["..KKKK", "KKW0HK", "K.W01.", ".KW12."], ef=[".KKKK.", "KW0HKK", ".W01.K", ".W12K."],
              bn=[".BBB.", "B...."], bf=["BBB..", "...B."], mo=[".l."], dy=0.0),
    'O': dict(en=["..KKKK", "KKW0HK", "..lW1l"], ef=[".KKKK", "W0HKK", "lW1l."],
              bn=["BBBBB", "B...."], bf=["BBBBB", "....B"], mo=[".ll"], dy=0.9),
}
MINI_TYPE = {'M': 'M', 'S': 'M', 'F': 'F', 'F2': 'F', 'O': 'O', 'V': 'O', 'G': 'O', 'T': 'O'}


def mini_scene(cid):
    s = CHARS[cid].get('mini_s', MINI_S)
    cx, cy = CHARS[cid].get('mini_c', MINI_C[:2])
    sc = Scene(MINI, MINI, scale=s, ox=MINI_C[2] - cx * s, oy=MINI_C[3] - cy * s)
    CHARS[cid]['build'](sc)
    sc.overlays = []          # 1:1 像素贴花不缩放，小头像里不画
    sc.render()
    return sc


def render_mini(cid):
    """32×32 脸部特写：同一套形状按 MINI_S 重绘 + 小五官模板。"""
    spec = CHARS[cid]
    sc = mini_scene(cid)
    rgba = sc.rgba.copy()
    cm = feature_cmap(spec['skin'], spec['eye'], spec.get('brow_ramp', spec['hair']), spec['brow_col'])
    on = sc.ids('face', *spec.get('feat_on', ()))
    ft = MINI_FEAT[MINI_TYPE[spec['eyes']]]
    dy = ft['dy']

    def put(anchor, rows, ids):
        x, y = sc.X(*anchor)
        stamp(rgba, sc.owner, ids, int(round(x)), int(round(y)), (rows, 0, 0), cm)
    for mx, my, rows in spec.get('mini_marks', ()):
        put((mx, my), rows, on)
    put((32.0, 32.0 + dy), ft['en'], on)
    put((47.5, 32.0 + dy), ft['ef'], on)
    put((31.0, 28.2 + dy * 0.6), ft['bn'], on)
    put((47.5, 28.2 + dy * 0.6), ft['bf'], on)
    mx, my = spec.get('mini_mouth', (44.0, spec['mouth'][1] + 1.0))
    put((mx, my), ft['mo'], sc.ids('face', *spec.get('mouth_on', ())))
    put((47.8, 40.0), ["s"], on)
    if spec.get('post'):
        spec['post'](sc, rgba, 'normal', '')
    return rgba


def build_sheet():
    rows = len(ORDER)
    Wt, Ht = SHEET_COLS * S, rows * S + MINI
    sheet = np.zeros((Ht, Wt, 4), np.uint8)
    frames = {}
    for r, cid in enumerate(ORDER):
        c = 0
        for ex in CHARS[cid]['exprs']:
            for fr in FRAME_KINDS:
                x, y = c * S, r * S
                sheet[y:y + S, x:x + S] = render_frame(cid, ex, fr)
                frames[frame_name(cid, ex, fr)] = [x, y, S, S, 0, 0]
                c += 1
    for i, cid in enumerate(ORDER):
        x, y = i * MINI, rows * S
        sheet[y:y + MINI, x:x + MINI] = render_mini(cid)
        frames[cid + '_mini'] = [x, y, MINI, MINI, 0, 0]
    Image.fromarray(sheet, 'RGBA').save(OUT_PNG, optimize=True)
    lines = ['  "%s": [%s]' % (k, ', '.join(str(v) for v in f)) for k, f in frames.items()]
    with open(OUT_JSON, 'w', encoding='utf-8') as fp:
        nl = chr(10)
        fp.write('{"frames": {' + nl + (',' + nl).join(lines) + nl + '}}' + nl)
    return sheet, frames


def allowed_colors():
    cols = {INK[:3], INK2[:3]}
    for r in list(PAL.values()) + list(EXTRA_PAL.values()):
        for c in r:
            cols.add(tuple(c[:3]))
    return cols


def validate(sheet, frames):
    """自检：无半透明、只用调色板色、无纯黑、三帧只差眼/口、底边平直。"""
    errs = []
    a = sheet[:, :, 3]
    if not np.isin(a, (0, 255)).all():
        errs.append('存在半透明像素')
    ok = allowed_colors()
    px = {tuple(c) for c in sheet[a == 255][:, :3].reshape(-1, 3)}
    bad = px - ok
    if bad:
        errs.append('调色板外颜色 %d 种: %s' % (len(bad), list(bad)[:5]))
    if (0, 0, 0) in px:
        errs.append('出现纯黑')
    for cid in ORDER:
        spec = CHARS[cid]
        for ex in spec['exprs']:
            x, y = frames[frame_name(cid, ex, '')][:2]
            base = sheet[y:y + S, x:x + S].astype(int)
            for fr in ('talk', 'blink'):
                fx, fy = frames[frame_name(cid, ex, fr)][:2]
                d = np.nonzero((sheet[fy:fy + S, fx:fx + S].astype(int) != base).any(-1))
                if len(d[0]):
                    ys, xs = d
                    if fr == 'talk' and (ys.min() < 40 or ys.max() > 56):
                        errs.append('%s_%s talk 改动超出嘴部 (y %d..%d)' % (cid, ex, ys.min(), ys.max()))
                    if fr == 'blink' and (ys.min() < 24 or ys.max() > 42):
                        errs.append('%s_%s blink 改动超出眼部 (y %d..%d)' % (cid, ex, ys.min(), ys.max()))
                elif fr == 'talk':
                    errs.append('%s_%s talk 与闭嘴帧相同' % (cid, ex))
            row = base[S - 1, :, 3]
            filled = np.nonzero(row)[0]
            if len(filled) < 40 or (filled.max() - filled.min() + 1) != len(filled):
                errs.append('%s_%s 底边不连续' % (cid, ex))
    return errs


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--preview', default='')
    ap.add_argument('--exprs', default='')
    ap.add_argument('--frames', default=',talk,blink')
    ap.add_argument('--cols', type=int, default=3)
    ap.add_argument('--scale', type=int, default=4)
    a = ap.parse_args()
    os.makedirs(PREV, exist_ok=True)
    if a.preview:
        ids = a.only.split(',') if a.only else ORDER
        imgs = []
        for cid in ids:
            exs = a.exprs.split(',') if a.exprs else CHARS[cid]['exprs']
            for ex in exs:
                if ex not in CHARS[cid]['exprs']:
                    continue
                for fr in a.frames.split(','):
                    imgs.append(to_img(render_frame(cid, ex, fr)))
        contact(imgs, a.cols, scale=a.scale).save(os.path.join(PREV, a.preview + '.png'))
        print('preview', len(imgs))
        return
    sheet, frames = build_sheet()
    errs = validate(sheet, frames)
    print('portraits.png %dx%d, %d frames' % (sheet.shape[1], sheet.shape[0], len(frames)))
    for e in errs:
        print('  !', e)
    if not errs:
        print('  自检通过：无半透明/无调色板外颜色/无纯黑/三帧只差眼口/底边平直')
    # 预览：全员 normal、全员小头像、整表缩略
    contact([to_img(render_frame(c, 'normal', '')) for c in ORDER], 7, scale=3).save(
        os.path.join(PREV, 'all_normal.png'))
    contact([to_img(render_mini(c)) for c in ORDER], 10, scale=4).save(os.path.join(PREV, 'all_mini.png'))
    Image.fromarray(sheet, 'RGBA').save(os.path.join(PREV, 'sheet_1x.png'))


if __name__ == '__main__':
    main()
