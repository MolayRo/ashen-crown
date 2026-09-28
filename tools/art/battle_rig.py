# -*- coding: utf-8 -*-
"""
《灰烬王冠》战斗动画 —— 部件木偶渲染核心。

流程：部件(Part) = 布尔遮罩 + 材质 + 深度 z + 分组
  1) 按 z 从后往前画到缓冲区（owner / level）
  2) 自动明暗：遮罩高斯模糊求外法线，与左上光源点积后量化成 1~4 阶（5 = 金属高光）
  3) 投影：前景部件在其右下方 1~2px 投下阴影（降一阶）
  4) 内描边：后方部件与前方（不同组）部件相邻的像素画成该材质最暗色
  5) 外描边：整体剪影外一圈 INK
所有颜色都来自 palette.py 色阶（材质 = 某色阶的 5 个色：描边、深影、阴影、基色、高光）。
"""
import math
import numpy as np
from palette import PAL, INK, INK2, hx

W, H = 96, 80
AX, AY = 48, 76
# 调试：用更大的画布测量越界量（BATTLE_DIAG_CANVAS=W,H,AX,AY）
import os as _os
if _os.environ.get('BATTLE_DIAG_CANVAS'):
    W, H, AX, AY = [int(v) for v in _os.environ['BATTLE_DIAG_CANVAS'].split(',')]

YY, XX = np.mgrid[0:H, 0:W]
PXC = XX + 0.5
PYC = YY + 0.5

_L = np.array([-0.6, -0.8])
LDIR = _L / np.linalg.norm(_L)


# ---------------------------------------------------------------- 材质
class Mat:
    """tones: [描边, 深影, 阴影, 基色, 高光]；spec 为金属高光色（可选）。"""

    def __init__(self, ramp, off=0, hi=0.34, sh=-0.30, deep=-0.95, spec=None, spec_th=0.75,
                 tones=None, name=''):
        if tones is None:
            r = PAL[ramp] if isinstance(ramp, str) else ramp
            tones = [r[min(len(r) - 1, off + i)] for i in range(5)]
        self.tones = [tuple(t) for t in tones]
        self.hi, self.sh, self.deep = hi, sh, deep
        self.spec = tuple(spec) if spec is not None else None
        self.spec_th = spec_th
        self.name = name or (ramp if isinstance(ramp, str) else 'custom')

    def c(self, i):
        if i >= 5:
            return self.spec or self.tones[4]
        return self.tones[max(0, i)]

    def shifted(self, d):
        """整体变暗/变亮 d 阶（新材质）。"""
        t = self.tones
        nt = [t[max(0, min(4, i + d))] if i > 0 else t[0] for i in range(5)]
        m = Mat(None, tones=nt, hi=self.hi, sh=self.sh, deep=self.deep, spec=self.spec, spec_th=self.spec_th)
        return m


def mat(name, off=0, **kw):
    return Mat(name, off, **kw)


def metal(name, off=0, **kw):
    """金属：对比更强，带高光点。"""
    r = PAL[name]
    spec = kw.pop('spec', PAL['grey'][5])
    return Mat(name, off, hi=kw.pop('hi', 0.26), sh=kw.pop('sh', -0.22), deep=kw.pop('deep', -0.70),
               spec=spec, spec_th=kw.pop('spec_th', 0.62), **kw)


# ---------------------------------------------------------------- 遮罩（光栅化，无抗锯齿）
def m_cap(p0, p1, r0, r1=None):
    """锥形胶囊（四肢）。"""
    if r1 is None:
        r1 = r0
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    l2 = dx * dx + dy * dy
    if l2 < 1e-6:
        t = np.zeros_like(PXC)
    else:
        t = np.clip(((PXC - x0) * dx + (PYC - y0) * dy) / l2, 0.0, 1.0)
    cx = x0 + t * dx
    cy = y0 + t * dy
    r = r0 + (r1 - r0) * t
    return (PXC - cx) ** 2 + (PYC - cy) ** 2 <= r * r


def m_poly(pts):
    inside = np.zeros((H, W), bool)
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if y0 == y1:
            continue
        cond = (y0 > PYC) != (y1 > PYC)
        xint = (x1 - x0) * (PYC - y0) / (y1 - y0) + x0
        inside ^= cond & (PXC < xint)
    return inside


def m_ell(c, rx, ry, ang=0.0):
    cx, cy = c
    ca, sa = math.cos(ang), math.sin(ang)
    u = (PXC - cx) * ca + (PYC - cy) * sa
    v = -(PXC - cx) * sa + (PYC - cy) * ca
    return (u / rx) ** 2 + (v / ry) ** 2 <= 1.0


def line_pts(p0, p1):
    x0, y0 = int(math.floor(p0[0])), int(math.floor(p0[1]))
    x1, y1 = int(math.floor(p1[0])), int(math.floor(p1[1]))
    pts = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return pts


def m_pts(pts):
    m = np.zeros((H, W), bool)
    for x, y in pts:
        if 0 <= x < W and 0 <= y < H:
            m[y, x] = True
    return m


def m_line(p0, p1):
    return m_pts(line_pts(p0, p1))


def m_arc(c, r, a0, a1, steps=None):
    """圆弧（1px），角度制，0=右，逆时针为负 y（屏幕坐标下按数学方向）。"""
    if steps is None:
        steps = max(8, int(abs(a1 - a0) / 180 * math.pi * r * 2))
    pts = []
    for i in range(steps + 1):
        a = math.radians(a0 + (a1 - a0) * i / steps)
        pts.append((c[0] + math.cos(a) * r, c[1] + math.sin(a) * r))
    m = np.zeros((H, W), bool)
    for i in range(len(pts) - 1):
        m |= m_line(pts[i], pts[i + 1])
    return m


def shift(a, dx, dy, fill):
    """out[y, x] = a[y + dy, x + dx]（越界填 fill）。"""
    out = np.full_like(a, fill)
    h, w = a.shape[:2]
    ys0, ys1 = max(0, -dy), min(h, h - dy)
    xs0, xs1 = max(0, -dx), min(w, w - dx)
    if ys0 < ys1 and xs0 < xs1:
        out[ys0:ys1, xs0:xs1] = a[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx]
    return out


def dilate4(m):
    return m | shift(m, 1, 0, False) | shift(m, -1, 0, False) | shift(m, 0, 1, False) | shift(m, 0, -1, False)


def gblur(a, sigma):
    r = max(1, int(math.ceil(sigma * 2.5)))
    xs = np.arange(-r, r + 1)
    k = np.exp(-(xs ** 2) / (2.0 * sigma * sigma))
    k /= k.sum()
    h, w = a.shape
    p = np.pad(a, r)
    t = np.zeros((h + 2 * r, w))
    for i, kv in enumerate(k):
        t += kv * p[:, i:i + w]
    out = np.zeros((h, w))
    for i, kv in enumerate(k):
        out += kv * t[i:i + h, :]
    return out


# ---------------------------------------------------------------- 部件
class Part:
    def __init__(self, mask, m=None, z=0.0, group=None, fixed=None, level=None, inherit=None,
                 sigma=1.0, bias=0.0, extra=None, lines=True, cast=True, recv=True, outline=True,
                 line_color=None, name='', nolit=False, despeckle=True):
        self.mask = mask
        self.mat = m
        self.z = z
        self.group = group
        self.fixed = fixed          # (H,W,4) 颜色数组：模板部件
        self.level = level          # 固定色阶（标量或数组）
        self.inherit = inherit      # 贴花：继承下方部件的色阶 + 偏移
        self.sigma = sigma
        self.bias = bias
        self.extra = extra          # 额外光照项（数组）
        self.lines = lines          # 是否在后方部件上画出自身轮廓线
        self.cast = cast            # 是否投影
        self.recv = recv            # 是否接受投影/轮廓线
        self.outline = outline      # 是否参与外描边
        self.line_color = line_color
        self.name = name
        self.nolit = nolit          # 不用高光（只有基色/阴影）
        self.despeckle = despeckle


def auto_levels(mask, m, sigma=1.0, bias=0.0, extra=None, nolit=False):
    b = gblur(mask.astype(np.float64), sigma)
    gy, gx = np.gradient(b)
    gmax = 1.0 / (sigma * math.sqrt(2 * math.pi))
    I = -(gx * LDIR[0] + gy * LDIR[1]) / gmax
    if extra is not None:
        I = I + extra
    I = I + bias
    lv = np.full(mask.shape, 3, np.int16)
    if not nolit:
        lv[I > m.hi] = 4
        if m.spec is not None:
            lv[I > m.spec_th] = 5
    lv[I < m.sh] = 2
    lv[I < m.deep] = 1
    return lv


def _despeckle(lv, mask):
    """去掉孤立的高光/阴影点。"""
    out = lv.copy()
    for val, repl in ((4, 3), (5, 4), (2, 3)):
        sel = (lv == val) & mask
        if not sel.any():
            continue
        cnt = np.zeros(lv.shape, np.int16)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                cnt += shift(((lv == val) | (lv == val + (1 if val >= 4 else -1))) & mask, dx, dy, False)
        out[sel & (cnt == 0)] = repl
    return out


CAST_OFFS = [(-1, -1), (-2, -2), (-1, -2), (-2, -1), (0, -2), (-2, 0)]
N4 = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def render(parts, post=(), outline_color=INK):
    """把部件列表合成为 (H,W,4) uint8 图像。"""
    n = len(parts)
    order = sorted(range(n), key=lambda i: parts[i].z)
    owner = np.full((H, W), -1, np.int32)
    matsrc = np.full((H, W), -1, np.int32)
    lvl = np.full((H, W), 3, np.int16)
    fixc = np.zeros((H, W, 4), np.uint8)
    for i in order:
        p = parts[i]
        m = p.mask
        if not m.any():
            continue
        if p.fixed is not None:
            owner[m] = i
            fixc[m] = p.fixed[m]
            lvl[m] = -1
        elif p.inherit is not None:
            base = lvl.copy()
            base[base < 1] = 3
            nv = np.clip(base + p.inherit, 1, 5)
            if p.mat is None:
                # 无自身材质：只在已有自动着色部件上生效，沿用下方材质
                m = m & (matsrc >= 0) & (lvl > 0)
            else:
                matsrc[m] = i
            owner[m] = i
            lvl[m] = nv[m]
        elif p.level is not None:
            owner[m] = i
            matsrc[m] = i
            if np.isscalar(p.level):
                lvl[m] = p.level
            else:
                lvl[m] = p.level[m]
        else:
            L = auto_levels(m, p.mat, p.sigma, p.bias, p.extra, p.nolit)
            if p.despeckle:
                L = _despeckle(L, m)
            owner[m] = i
            matsrc[m] = i
            lvl[m] = L[m]

    zarr = np.array([p.z for p in parts] + [-1e9])
    gids = {}
    gid = np.array([gids.setdefault(p.group if p.group is not None else ('#', i), len(gids))
                    for i, p in enumerate(parts)] + [-1])
    castf = np.array([p.cast for p in parts] + [False])
    linef = np.array([p.lines for p in parts] + [False])
    recvf = np.array([p.recv for p in parts] + [False])
    own = np.where(owner < 0, n, owner)
    zs = zarr[own]
    gs = gid[own]
    solid = owner >= 0
    auto = solid & (lvl > 0)

    # 投影
    shadow = np.zeros((H, W), bool)
    for dx, dy in CAST_OFFS:
        o2 = shift(own, dx, dy, n)
        cond = (o2 < n) & (zarr[o2] > zs) & (gid[o2] != gs) & castf[o2] & recvf[own]
        shadow |= cond
    sel = shadow & auto & (lvl >= 2)
    lvl[sel] -= 1
    lvl[shadow & auto & (lvl == 5)] = 3

    # 内描边
    lines = np.zeros((H, W), bool)
    for dx, dy in N4:
        o2 = shift(own, dx, dy, n)
        cond = (o2 < n) & (zarr[o2] > zs) & (gid[o2] != gs) & linef[o2] & recvf[own]
        lines |= cond
    lines &= solid

    img = np.zeros((H, W, 4), np.uint8)
    for i in order:
        p = parts[i]
        vis = owner == i
        if not vis.any():
            continue
        if p.fixed is not None:
            img[vis] = fixc[vis]
            lc = p.line_color if p.line_color is not None else INK2
            img[vis & lines] = lc
            continue
        L = lvl.copy()
        L[lines] = 0
        srcs = np.unique(matsrc[vis])
        for j in srcs:
            if j < 0:
                continue
            mm = parts[j].mat if parts[j].mat is not None else p.mat
            tones = np.array([mm.c(k) for k in range(6)], np.uint8)
            sel = vis & (matsrc == j)
            img[sel] = tones[np.clip(L[sel], 0, 5)]
        if p.line_color is not None:
            img[vis & lines] = p.line_color

    # 外描边
    src = np.zeros((H, W), bool)
    outf = np.array([p.outline for p in parts] + [False])
    src = solid & outf[own]
    ol = dilate4(src) & ~solid
    img[ol] = outline_color

    safe = np.zeros((H, W), bool)
    safe[1:AY + 2, 1:W - 1] = True
    for item in post:
        mask, colors, mode = item
        mask = mask & safe
        if mode == 'under':
            sel = mask & (img[:, :, 3] == 0)
        else:
            sel = mask
        if isinstance(colors, np.ndarray) and colors.ndim == 3:
            img[sel] = colors[sel]
        else:
            img[sel] = colors
    return img


# ---------------------------------------------------------------- 模板（手绘像素）
def stamp(rows, legend, pos, anchor=(0, 0), flip=False):
    """rows: 字符串列表；legend: 字符 -> RGBA；pos: 画布坐标（模板 anchor 点对准 pos）。
    返回 (mask, colors)。"""
    mask = np.zeros((H, W), bool)
    col = np.zeros((H, W, 4), np.uint8)
    ox = int(round(pos[0] - anchor[0]))
    oy = int(round(pos[1] - anchor[1]))
    wmax = max(len(r) for r in rows)
    for j, r in enumerate(rows):
        for i, ch in enumerate(r):
            if ch in ('.', ' '):
                continue
            c = legend.get(ch)
            if c is None:
                raise KeyError('模板字符未定义: %r' % ch)
            x = ox + ((wmax - 1 - i) if flip else i)
            y = oy + j
            if 0 <= x < W and 0 <= y < H:
                mask[y, x] = True
                col[y, x] = c
    return mask, col


# ---------------------------------------------------------------- 几何工具
def V(x, y):
    return np.array([float(x), float(y)])


def adir(deg):
    """方向角（度）：0=下，90=前(左)，180=上，-90=后(右)。"""
    r = math.radians(deg)
    return V(-math.sin(r), math.cos(r))


def ang_of(v):
    return math.degrees(math.atan2(-v[0], v[1]))


def perp(d):
    """d 的法向（d 顺时针转 90°，屏幕坐标）。"""
    return V(-d[1], d[0])


def ik2(root, target, l1, l2, bend=1.0):
    """两段 IK：返回关节点与实际末端。bend=+1 关节偏向“前方”（以 root->target 方向左手侧）。"""
    root = V(*root)
    target = V(*target)
    v = target - root
    d = float(np.linalg.norm(v))
    if d < 1e-6:
        v = V(0, 1)
        d = 1e-6
    u = v / d
    dmax = (l1 + l2) * 0.999
    if d > dmax:
        target = root + u * dmax
        d = dmax
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    hh = math.sqrt(max(0.0, l1 * l1 - a * a))
    n = V(-u[1], u[0])  # 下方向时 n 指向左（前）
    if u[1] < 0:
        pass
    joint = root + u * a + n * hh * bend
    return joint, target


def rot(v, deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return V(v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def to_img(arr):
    from PIL import Image
    return Image.fromarray(arr, 'RGBA')
