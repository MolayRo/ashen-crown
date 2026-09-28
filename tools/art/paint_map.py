# -*- coding: utf-8 -*-
"""
《灰烬王冠》战斗地图绘制器：按地形字符画出整张地图（3 帧动画 + 可变格改变后的 _alt）。

用法：
  python tools/art/paint_map.py tools/maps/ch1.json [更多.json ...]
  python tools/art/paint_map.py                 处理 tools/maps/ 下全部 *.json
  python tools/art/paint_map.py --samples       只处理 sample_*.json
  python tools/art/paint_map.py --no-samples    跳过 sample_*.json（只处理正式章节地图）
  --no-preview   不输出放大预览（预览在 tools/art/preview/maps/）

输入：{"id": "ch1", "theme": "plains|snow|indoor|castle", "rows": ["..TT..~~..", ...]}
可选："art": {
  "bridge": "wood"|"stone",            全图桥梁样式（默认：含断桥 B 的桥段与 castle 主题为石桥，其余木桥）
  "stone_bridges": [[x,y],...],        指定某段桥（含该格的整段）为石桥
  "wood_bridges":  [[x,y],...],        指定某段桥为木桥
  "roofs": {"x,y": "red"|"blue"|"thatch"}   指定含该格的房屋屋顶样式（默认按位置随机）
}
输出：assets/maps/<id>_0.png _1.png _2.png （3 帧；只有水面波光、火把/烛光、旗帜不同）
      assets/maps/<id>_alt.png           （D 门→打开、C 宝箱→已开、V 村庄→焚毁；改变只落在该格 16×16 内）
"""
import os
import sys
import json
import math
import glob
import zlib
import random
import argparse

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from palette import PAL, INK, INK2  # noqa: E402

TS = 16
MAPS_DIR = os.path.join(ROOT, 'tools', 'maps')
OUT_DIR = os.path.join(ROOT, 'assets', 'maps')
PREV_DIR = os.path.join(HERE, 'preview', 'maps')

G = PAL['grass']; FO = PAL['forest']; WA = PAL['water']; EA = PAL['earth']
RO = PAL['rock']; SN = PAL['snow']; ST = PAL['stone']; WO = PAL['wood']
GO = PAL['gold']; CA = PAL['carpet']; FI = PAL['fire']; IR = PAL['iron']
CW = PAL['cloth_white']; RR = PAL['roof_red']; RB = PAL['roof_blue']
CB = PAL['cloth_black']; CR = PAL['cloth_crimson']; SK = PAL['cloth_sky']

# 材质层（用于阴影只落在地面上等判断）
M_GROUND, M_ROAD, M_WATER, M_WALL, M_OBJ, M_BRIDGE = 1, 2, 3, 4, 5, 6

WET = set('~_=B')
MOUNT = set('^A')
WALLS = set('#DG')
HOUSE = set('HV')
MUTABLE = set('DCV')

# ------------------------------------------------------------------ 颜色工具
_SHADE_ORDER = ['grass', 'snow', 'earth', 'stone', 'rock', 'water', 'forest', 'wood',
                'roof_red', 'roof_blue', 'carpet', 'gold', 'iron', 'steel', 'grey',
                'cloth_white', 'fire', 'cloth_black', 'cloth_crimson', 'cloth_sky']
_SHADE = {}
for _n in _SHADE_ORDER:
    for _i, _c in enumerate(PAL[_n]):
        _SHADE.setdefault(_c[:3], (_n, _i))


def shade(c, d):
    """沿所在色阶移动 d 级（负数变暗）。"""
    k = _SHADE.get(tuple(c[:3]))
    if k is None:
        return c
    n, i = k
    r = PAL[n]
    return r[max(0, min(len(r) - 1, i + d))]


# ------------------------------------------------------------------ 随机/噪声
def ih(*a):
    h = 0x811C9DC5
    for v in a:
        h = ((h ^ (int(v) & 0xFFFFFFFF)) * 0x01000193) & 0xFFFFFFFF
        h ^= h >> 13
        h = (h * 0x5BD1E995) & 0xFFFFFFFF
        h ^= h >> 15
    return h


def fr(*a):
    return ih(*a) / 4294967296.0


def nh(a, b, s):
    a = np.asarray(a).astype(np.uint64)
    b = np.asarray(b).astype(np.uint64)
    h = (a * np.uint64(374761393) + b * np.uint64(668265263) + np.uint64(s & 0xFFFFFFFF)) & np.uint64(0xFFFFFFFF)
    h = ((h ^ (h >> np.uint64(13))) * np.uint64(1274126177)) & np.uint64(0xFFFFFFFF)
    return h ^ (h >> np.uint64(16))


def value_noise(w, h, period, seed):
    rng = np.random.RandomState(seed & 0x7FFFFFFF)
    gw = w // period + 3
    gh = h // period + 3
    g = rng.rand(gh, gw)
    ys = np.arange(h) / period
    xs = np.arange(w) / period
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    fy = ys - y0
    fx = xs - x0
    fy = fy * fy * (3 - 2 * fy)
    fx = fx * fx * (3 - 2 * fx)
    g00 = g[np.ix_(y0, x0)]
    g01 = g[np.ix_(y0, x0 + 1)]
    g10 = g[np.ix_(y0 + 1, x0)]
    g11 = g[np.ix_(y0 + 1, x0 + 1)]
    top = g00 + (g01 - g00) * fx[None, :]
    bot = g10 + (g11 - g10) * fx[None, :]
    return top + (bot - top) * fy[:, None]


def box_blur(a, r):
    if r <= 0:
        return a.astype(np.float32)
    k = 2 * r + 1
    p = np.pad(a.astype(np.float32), r, mode='edge')
    c = np.cumsum(p, axis=0)
    c = np.concatenate([np.zeros((1, c.shape[1]), np.float32), c], axis=0)
    a1 = (c[k:] - c[:-k]) / k
    c = np.cumsum(a1, axis=1)
    c = np.concatenate([np.zeros((c.shape[0], 1), np.float32), c], axis=1)
    return (c[:, k:] - c[:, :-k]) / k


def upscale(cm):
    return np.kron(cm.astype(np.float32), np.ones((TS, TS), np.float32))


def clean_mask(m, iters=2):
    for _ in range(iters):
        p = np.pad(m, 1, mode='edge')
        n = (p[:-2, 1:-1].astype(np.int32) + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:])
        m = np.where(m & (n <= 1), False, m)
        m = np.where(~m & (n >= 3), True, m)
    return m


def erode4(m):
    p = np.pad(m, 1, mode='edge')
    return m & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]


def dilate4(m):
    p = np.pad(m, 1, mode='edge')
    return m | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]


def dist_dir(mask, d):
    """每个 True 像素沿方向 d 到最近 False 的距离（紧邻为 1）；False 处为 0。出图边界视为延续。"""
    H, W = mask.shape
    out = np.zeros((H, W), np.int32)
    if d in ('u', 'd'):
        order = range(H) if d == 'u' else range(H - 1, -1, -1)
        prev = np.full(W, 60, np.int32)
        for y in order:
            cur = np.where(mask[y], prev + 1, 0)
            out[y] = cur
            prev = cur
    else:
        order = range(W) if d == 'l' else range(W - 1, -1, -1)
        prev = np.full(H, 60, np.int32)
        for x in order:
            cur = np.where(mask[:, x], prev + 1, 0)
            out[:, x] = cur
            prev = cur
    return out


# ------------------------------------------------------------------ 画布
class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.c = np.zeros((h, w, 4), np.uint8)
        self.mat = np.zeros((h, w), np.uint8)

    def put(self, x, y, col, mat=M_OBJ):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.c[y, x] = col
            self.mat[y, x] = mat

    def get(self, x, y):
        x = min(max(x, 0), self.w - 1)
        y = min(max(y, 0), self.h - 1)
        v = self.c[y, x]
        return (int(v[0]), int(v[1]), int(v[2]), int(v[3]))

    def rect(self, x0, y0, x1, y1, col, mat=M_OBJ):
        """含两端的矩形。"""
        x0 = max(0, x0); y0 = max(0, y0)
        x1 = min(self.w - 1, x1); y1 = min(self.h - 1, y1)
        if x1 < x0 or y1 < y0:
            return
        self.c[y0:y1 + 1, x0:x1 + 1] = col
        self.mat[y0:y1 + 1, x0:x1 + 1] = mat

    def darken(self, x, y, n=1, only=(M_GROUND, M_ROAD)):
        if 0 <= x < self.w and 0 <= y < self.h and self.mat[y, x] in only:
            self.c[y, x] = shade(self.get(x, y), -n)


def sprite(rows, legend):
    pts = []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in '. ':
                continue
            pts.append((x, y, legend[ch]))
    return pts


def blit(cv, pts, ox, oy, mat=M_OBJ, flip_w=0):
    for x, y, col in pts:
        if flip_w:
            x = flip_w - 1 - x
        cv.put(ox + x, oy + y, col, mat)


# ------------------------------------------------------------------ 地图
class Map:
    def __init__(self, data):
        self.id = data['id']
        self.theme = data.get('theme', 'plains')
        if self.theme not in ('plains', 'snow', 'indoor', 'castle'):
            print('  [警告] 未知主题 %r，按 plains 处理' % self.theme)
            self.theme = 'plains'
        rows = data['rows']
        self.h = len(rows)
        self.w = max(len(r) for r in rows)
        if any(len(r) != self.w for r in rows):
            print('  [警告] %s 行长度不一致，短行用 "." 补齐' % self.id)
        self.g = [r.ljust(self.w, '.') for r in rows]
        self.art = data.get('art') or {}
        self.seed = zlib.crc32(self.id.encode('utf-8')) & 0x7FFFFFFF
        known = set('.,"ThA^~_=B#+c|DCVHFGKSxrfaP')
        bad = sorted(set(''.join(self.g)) - known)
        if bad:
            print('  [警告] 未知地形字符 %s，按平原处理' % ''.join(bad))
            self.g = [''.join('.' if ch in bad else ch for ch in r) for r in self.g]

    def inb(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def at(self, x, y):
        x = 0 if x < 0 else (self.w - 1 if x >= self.w else x)
        y = 0 if y < 0 else (self.h - 1 if y >= self.h else y)
        return self.g[y][x]

    def cells(self, chars):
        for y in range(self.h):
            for x in range(self.w):
                if self.g[y][x] in chars:
                    yield x, y

    def mask(self, chars):
        a = np.zeros((self.h, self.w), bool)
        for x, y in self.cells(chars):
            a[y, x] = True
        return a


UNDER_DIRECT = {'.': 'ground', ',': 'ground', '"': 'ground', '+': 'floor', 'P': 'prison', 'c': 'carpet'}
UNDER_OUT = set('ThH^AVFx~_=Bf')


def compute_under(m):
    """每格底下铺什么（物件格按邻居投票）。"""
    default = 'floor' if m.theme == 'indoor' else 'ground'
    U = [[None] * m.w for _ in range(m.h)]
    for y in range(m.h):
        for x in range(m.w):
            ch = m.g[y][x]
            if ch in UNDER_DIRECT:
                U[y][x] = UNDER_DIRECT[ch]
            elif ch in UNDER_OUT:
                U[y][x] = 'ground'
    # 王座邻接地毯、或宝箱/祭坛/楼梯夹在地毯中间（≥2 个正交邻格是地毯）时，底下铺地毯
    for x, y in m.cells('KCaS'):
        n = sum(1 for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))
                if m.inb(x + dx, y + dy) and m.g[y + dy][x + dx] == 'c')
        if n >= (1 if m.g[y][x] == 'K' else 2):
            U[y][x] = 'carpet'
    for _ in range(6):
        changed = False
        for y in range(m.h):
            for x in range(m.w):
                if U[y][x] is not None:
                    continue
                votes = {}
                for dx, dy, w in ((0, -1, 2), (1, 0, 2), (0, 1, 2), (-1, 0, 2),
                                  (1, 1, 1), (-1, 1, 1), (1, -1, 1), (-1, -1, 1)):
                    nx, ny = x + dx, y + dy
                    if m.inb(nx, ny) and U[ny][nx] is not None and m.g[ny][nx] not in WALLS:
                        u = U[ny][nx]
                        if u == 'carpet' and m.g[y][x] != 'K':
                            u = 'floor'
                        votes[u] = votes.get(u, 0) + w
                if votes:
                    U[y][x] = max(sorted(votes), key=lambda k: votes[k])
                    changed = True
        if not changed:
            break
    for y in range(m.h):
        for x in range(m.w):
            if U[y][x] is None:
                U[y][x] = default
    return U


def components(m, chars, conn4=True):
    seen = set()
    out = []
    for y in range(m.h):
        for x in range(m.w):
            if (x, y) in seen or m.g[y][x] not in chars:
                continue
            stack = [(x, y)]
            seen.add((x, y))
            comp = []
            while stack:
                cx, cy = stack.pop()
                comp.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if m.inb(nx, ny) and (nx, ny) not in seen and m.g[ny][nx] in chars:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            out.append(sorted(comp, key=lambda p: (p[1], p[0])))
    return out


# ------------------------------------------------------------------ 渲染上下文
class Ctx:
    def __init__(self, m, frame=0, alt=False):
        self.m = m
        self.frame = frame
        self.alt = alt
        self.th = m.theme
        self.snow = m.theme == 'snow'
        self.W = m.w * TS
        self.H = m.h * TS
        self.cv = Canvas(self.W, self.H)
        self.seed = m.seed
        self.under = compute_under(m)
        if self.snow:
            self.gb, self.gd, self.gl, self.gdd = SN[3], SN[2], SN[4], SN[1]
        else:
            self.gb, self.gd, self.gl, self.gdd = G[4], G[3], G[5], G[2]
        self.anim_cells = set()   # 带动画像素的格子（自检用）

    def is_outdoor(self, x, y):
        ch = self.m.at(x, y)
        if ch in WALLS:
            return False
        return self.under[min(max(y, 0), self.m.h - 1)][min(max(x, 0), self.m.w - 1)] == 'ground'


# ================================================================== 地面
TUFTS = [
    ['d.d',
     '.d.'],
    ['.l..',
     'd.d.',
     '.d.d'],
    ['l.l.l',
     'd.d.d',
     '.d.d.'],
    ['..l',
     'd.d',
     '.d.'],
]
SNOW_DETAILS = [
    ['.lll.',
     'l...d',
     '.ddd.'],
    ['..ll',
     'dd..'],
    ['ll..',
     '..dd'],
]


def paint_ground(R):
    m, cv = R.m, R.cv
    code = {'ground': 1, 'floor': 2, 'prison': 3, 'carpet': 4}
    U = np.array([[code[R.under[y][x]] for x in range(m.w)] for y in range(m.h)], np.uint8)
    Up = np.kron(U, np.ones((TS, TS), np.uint8))
    R.Up = Up
    c = cv.c
    c[Up == 1] = R.gb
    if (Up == 2).any():
        pat = floor_pattern(R, 'castle' if R.th == 'castle' else 'stone')
        sel = Up == 2
        c[sel] = pat[sel]
    if (Up == 3).any():
        pat = floor_pattern(R, 'prison')
        sel = Up == 3
        c[sel] = pat[sel]
    cv.mat[:] = M_GROUND
    if (Up == 4).any():
        paint_carpets(R)
    ground_details(R)


def lv_colors(level, ramp, H, W):
    out = np.zeros((H, W, 4), np.uint8)
    for i, col in enumerate(ramp):
        out[level == i] = col
    return out


def floor_pattern(R, kind):
    Hp, Wp = R.H, R.W
    yy, xx = np.mgrid[0:Hp, 0:Wp]
    if kind == 'castle':
        # 王城大厅：与格子对齐的大方砖 + 暖色大理石，隔块有菱形嵌花
        r = RO
        xin = xx % 16
        yin = yy % 16
        lv = np.full((Hp, Wp), 4)
        chk = ((xx // 16) + (yy // 16)) % 2 == 0
        dia = np.abs(xin - 8) + np.abs(yin - 8)
        lv[chk & (dia <= 3)] = 5
        lv[chk & (dia == 4)] = 3
        lv[(~chk) & (dia <= 1)] = 3
        lv[(yin == 1) | (xin == 1)] = 5
        lv[(yin == 15) | (xin == 15)] = 3
        lv[(yin == 0) | (xin == 0)] = 2
        return lv_colors(lv, r, Hp, Wp)
    # 方形石板（修道院）/ 牢房：8×8 对齐网格，部分相邻两块合并成 16×8 / 8×16，每块有斜角亮暗边
    ty = yy // 8
    tx = xx // 8
    yin = yy % 8
    xin = xx % 8
    salt = R.seed + (7 if kind == 'prison' else 0)
    hb = nh(tx // 2, ty // 2, salt)
    mode = hb % 5          # 0: 横向合并 1: 纵向合并 其余：四块独立
    # 该像素所在石块的局部坐标（lx, ly）与尺寸（w, h）
    lx = xin.copy()
    ly = yin.copy()
    w = np.full(xx.shape, 8)
    h = np.full(xx.shape, 8)
    horiz = mode == 0
    vert = mode == 1
    lx = np.where(horiz, xx % 16, lx)
    w = np.where(horiz, 16, w)
    ly = np.where(vert, yy % 16, ly)
    h = np.where(vert, 16, h)
    sid = np.where(horiz, ty * 1000 + tx // 2, np.where(vert, (ty // 2) * 1000 + tx + 500, ty * 1000 + tx))
    h2 = nh(sid, sid // 7, salt + 99)
    if kind == 'prison':
        body, hi, sh, seam = 2, 3, 1, 0
    else:
        body, hi, sh, seam = 3, 4, 2, 1
    lv = np.full((Hp, Wp), body)
    darkstone = (h2 % 13) == 3
    lightstone = (h2 % 23) == 5
    lv[darkstone] = body - 1
    if kind != 'prison':
        lv[lightstone] = body + 1
    if kind == 'prison':
        lv[(ly == 1) | (lx == 1)] = np.where(darkstone, body, hi)[(ly == 1) | (lx == 1)]
        lv[(ly == h - 1) | (lx == w - 1)] = sh
        lv[(ly == 0) | (lx == 0)] = seam
    else:
        lv[(ly == 1) & (lx > 0)] = np.where(darkstone, body, hi)[(ly == 1) & (lx > 0)]
        lv[(ly == 0) | (lx == 0)] = sh
    # 裂纹
    crack = ((h2 >> np.uint64(5)) % 23) == 2
    cxo = ((h2 >> np.uint64(9)) % 3).astype(np.int64) + 2
    lv[crack & (ly >= 2) & (ly <= 5) & (lx == cxo + (ly - 2) // 2)] = seam
    out = lv_colors(lv, ST, Hp, Wp)
    if kind == 'prison':
        # 稻草与污渍
        hh = nh(xx // 3, yy // 2, R.seed + 5)
        straw = ((hh % 23) == 0) & (ly > 1) & (lx > 1)
        out[straw] = EA[3]
        straw2 = ((hh % 23) == 1) & (ly > 1) & (lx > 1)
        out[straw2] = EA[2]
    return out


def paint_carpets(R):
    m, cv = R.m, R.cv

    def isc(x, y):
        x = min(max(x, 0), m.w - 1)
        y = min(max(y, 0), m.h - 1)
        return R.under[y][x] == 'carpet'

    for y in range(m.h):
        for x in range(m.w):
            if R.under[y][x] != 'carpet':
                continue
            X, Y = x * TS, y * TS
            n, s, w, e = isc(x, y - 1), isc(x, y + 1), isc(x - 1, y), isc(x + 1, y)
            for py in range(TS):
                for px in range(TS):
                    gx, gy = X + px, Y + py
                    # 花纹：斜格菱形
                    u = (gx + gy) % 8
                    v = (gx - gy) % 8
                    col = CA[3]
                    if u == 0 or v == 0:
                        col = CA[2]
                    if (gx % 8 == 4) and (gy % 8 == 0):
                        col = GO[2]
                    # 边饰
                    edge = None
                    if not w and px <= 2:
                        edge = px
                    if not e and px >= 13:
                        edge = 15 - px if edge is None else min(edge, 15 - px)
                    if not n and py <= 2:
                        edge = py if edge is None else min(edge, py)
                    if not s and py >= 13:
                        edge = 15 - py if edge is None else min(edge, 15 - py)
                    if edge is not None:
                        col = (CA[1], GO[3], CA[4])[edge] if edge < 3 else col
                        if edge == 1 and ((not n and py == 1) or (not w and px == 1)):
                            col = GO[4]
                    cv.put(gx, gy, col, M_GROUND)
            # 圆角
            for cxp, cyp, cond in ((0, 0, not n and not w), (15, 0, not n and not e),
                                   (0, 15, not s and not w), (15, 15, not s and not e)):
                if cond:
                    under = floor_pattern_pixel(R, X + cxp, Y + cyp)
                    cv.put(X + cxp, Y + cyp, under, M_GROUND)


def floor_pattern_pixel(R, x, y):
    if getattr(R, '_floor_pat', None) is None:
        R._floor_pat = floor_pattern(R, 'castle' if R.th == 'castle' else 'stone')
    v = R._floor_pat[y, x]
    return (int(v[0]), int(v[1]), int(v[2]), 255)


def ground_details(R):
    m, cv = R.m, R.cv
    d, l, e = R.gd, R.gl, R.gdd
    leg = {'d': d, 'l': l, 'e': e}
    for y in range(m.h):
        for x in range(m.w):
            ch = m.g[y][x]
            if R.under[y][x] != 'ground':
                continue
            X, Y = x * TS, y * TS
            if ch == ',':
                paint_flowers(R, x, y)
                continue
            if ch not in '."T':
                continue
            v = ih(x, y, R.seed, 1) % 12
            if ch == 'T':
                v = v % 4 + 8   # 林间少量草丛
            if R.snow:
                if v >= 7:
                    k = ih(x, y, 2) % len(SNOW_DETAILS)
                    spr = SNOW_DETAILS[k]
                    ox = 2 + ih(x, y, 3) % (12 - len(spr[0]))
                    oy = 2 + ih(x, y, 4) % 10
                    blit(cv, sprite(spr, leg), X + ox, Y + oy, M_GROUND)
                if v == 11:
                    # 雪中露出的小石子
                    ox = 3 + ih(x, y, 5) % 9
                    oy = 3 + ih(x, y, 6) % 9
                    cv.put(X + ox, Y + oy, ST[4], M_GROUND)
                    cv.put(X + ox + 1, Y + oy, ST[3], M_GROUND)
                    cv.put(X + ox, Y + oy + 1, ST[2], M_GROUND)
                    cv.put(X + ox + 1, Y + oy + 1, ST[1], M_GROUND)
                continue
            nt = 0
            if v in (6, 7, 8):
                nt = 1
            elif v in (9, 10):
                nt = 2
            for i in range(nt):
                k = ih(x, y, 10 + i) % len(TUFTS)
                spr = TUFTS[k]
                ox = 1 + ih(x, y, 20 + i) % (14 - len(spr[0]))
                oy = 1 + ih(x, y, 30 + i) % (14 - len(spr))
                if i == 1:
                    ox = (ox + 7) % (14 - len(spr[0])) + 1
                blit(cv, sprite(spr, leg), X + ox, Y + oy, M_GROUND)
            if v == 11 and ch == '.':
                # 小石子
                ox = 3 + ih(x, y, 7) % 9
                oy = 3 + ih(x, y, 8) % 9
                cv.put(X + ox, Y + oy, RO[4], M_GROUND)
                cv.put(X + ox + 1, Y + oy, RO[3], M_GROUND)
                cv.put(X + ox + 1, Y + oy + 1, RO[2], M_GROUND)
                cv.put(X + ox, Y + oy + 1, G[3] if not R.snow else SN[2], M_GROUND)


FLOWER_COLS = [(CW[4], CW[2]), (GO[4], GO[2]), (CA[4], CA[2]),
               (PAL['magic_dark'][4], PAL['magic_dark'][3]), (SK[4], SK[3])]


def paint_flowers(R, x, y):
    cv = R.cv
    X, Y = x * TS, y * TS
    if R.snow:
        # 雪地“花草”：探出雪面的枯草与小石
        for i in range(3):
            ox = 2 + ih(x, y, 40 + i) % 11
            oy = 3 + ih(x, y, 50 + i) % 10
            for k in range(3):
                cv.put(X + ox + k - 1, Y + oy - (1 if k == 1 else 0), EA[3] if k != 2 else EA[2], M_GROUND)
                cv.put(X + ox + k - 1, Y + oy + 1, EA[2], M_GROUND)
            cv.put(X + ox - 1, Y + oy + 2, SN[2], M_GROUND)
            cv.put(X + ox + 1, Y + oy + 2, SN[2], M_GROUND)
        return
    base = ih(x, y, R.seed, 60)
    ncl = 3 + base % 2
    spots = [(3, 3), (10, 4), (5, 10), (11, 11), (8, 7)]
    k0 = base % 5
    for i in range(ncl):
        sx, sy = spots[(k0 + i * 2) % 5]
        sx += ih(x, y, 70 + i) % 3 - 1
        sy += ih(x, y, 80 + i) % 3 - 1
        pc, pd = FLOWER_COLS[(base >> 4) % 5] if i % 2 == 0 else FLOWER_COLS[(base >> 7) % 5]
        # 叶
        for lx, ly in ((-2, 1), (2, 1), (-1, 2), (1, 2)):
            cv.put(X + sx + lx, Y + sy + ly, G[3], M_GROUND)
        cv.put(X + sx, Y + sy + 2, G[2], M_GROUND)
        # 花瓣（十字）+ 花心
        cv.put(X + sx, Y + sy - 1, pc, M_GROUND)
        cv.put(X + sx - 1, Y + sy, pc, M_GROUND)
        cv.put(X + sx + 1, Y + sy, pd, M_GROUND)
        cv.put(X + sx, Y + sy + 1, pd, M_GROUND)
        cv.put(X + sx, Y + sy, GO[3] if pc != GO[4] else CA[3], M_GROUND)


# ================================================================== 道路
ROAD_LINK = set('"=BVGFSD')


def paint_roads(R):
    m, cv = R.m, R.cv
    cells = list(m.cells('"'))
    if not cells:
        return
    mask = np.zeros((R.H, R.W), bool)
    ins = 2
    for x, y in cells:
        X, Y = x * TS, y * TS
        mask[Y + ins:Y + TS - ins, X + ins:X + TS - ins] = True
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nx, ny = x + dx, y + dy
            link = (not m.inb(nx, ny)) or m.g[ny][nx] in ROAD_LINK
            if not link:
                continue
            if dy == -1:
                mask[Y:Y + ins, X + ins:X + TS - ins] = True
            elif dy == 1:
                mask[Y + TS - ins:Y + TS, X + ins:X + TS - ins] = True
            elif dx == -1:
                mask[Y + ins:Y + TS - ins, X:X + ins] = True
            else:
                mask[Y + ins:Y + TS - ins, X + TS - ins:X + TS] = True
            if m.inb(nx, ny) and m.g[ny][nx] in 'VFGSD':
                NX, NY = nx * TS, ny * TS
                dep = 3
                if dy == -1:
                    mask[NY + TS - dep:NY + TS, NX + 3:NX + TS - 3] = True
                elif dy == 1:
                    mask[NY:NY + dep, NX + 3:NX + TS - 3] = True
                elif dx == -1:
                    mask[NY + 3:NY + TS - 3, NX + TS - dep:NX + TS] = True
                else:
                    mask[NY + 3:NY + TS - 3, NX:NX + dep] = True
    # 并排的道路格之间补上格角（例如两格宽的路一起通向门/桥时，中缝上端不留缺口）
    def linkp(nx, ny):
        return (not m.inb(nx, ny)) or m.g[ny][nx] in ROAD_LINK
    for x, y in cells:
        X, Y = x * TS, y * TS
        for dx, dy in ((1, -1), (1, 1), (-1, -1), (-1, 1)):
            if linkp(x + dx, y) and linkp(x, y + dy) and linkp(x + dx, y + dy):
                xs_ = slice(X + TS - ins, X + TS) if dx > 0 else slice(X, X + ins)
                ys_ = slice(Y + TS - ins, Y + TS) if dy > 0 else slice(Y, Y + ins)
                mask[ys_, xs_] = True
    sm = box_blur(box_blur(mask, 2), 2)
    noise = value_noise(R.W, R.H, 5, R.seed + 11)
    rm = sm > 0.5 + (noise - 0.5) * 0.45
    rm &= dilate4(dilate4(mask))
    rm = clean_mask(rm)
    R.road_mask = rm
    c = cv.c
    inner = erode4(rm)
    edge = rm & ~inner
    if R.th in ('castle', 'indoor'):
        # 铺石路
        yy, xx = np.mgrid[0:R.H, 0:R.W]
        row = yy // 4
        off = (row % 2) * 3
        seam = ((yy % 4) == 0) | (((xx + off) % 6) == 0)
        hi = ((yy % 4) == 1) | (((xx + off) % 6) == 1)
        pr = RO if R.th == 'castle' else ST
        c[rm] = pr[4]
        c[rm & hi] = pr[5]
        c[rm & seam] = pr[3]
        c[edge] = pr[2]
    elif R.snow:
        c[rm] = SN[2]
        c[edge] = ST[3]
        yy, xx = np.mgrid[0:R.H, 0:R.W]
        hh = nh(xx // 2, yy, R.seed + 3)
        spk = rm & inner & ((hh % 9) == 0)
        c[spk] = SN[1]
        spk2 = rm & inner & ((hh % 9) == 1)
        c[spk2] = SN[3]
        spk3 = rm & inner & ((hh % 41) == 2)
        c[spk3] = EA[2]
        outer = dilate4(rm) & ~rm & (cv.mat == M_GROUND) & (R.Up == 1)
        c[outer] = SN[4]
    else:
        c[rm] = EA[4]
        # 路面上缘阴影（下凹的路），下缘亮
        up = np.zeros_like(rm)
        up[1:] = rm[1:] & ~rm[:-1]
        c[edge] = EA[3]
        yy, xx = np.mgrid[0:R.H, 0:R.W]
        hh = nh(xx, yy, R.seed + 3)
        spk = inner & ((hh % 29) == 0)
        c[spk] = EA[3]
        spk2 = inner & ((hh % 29) == 1)
        c[spk2] = EA[2]
        # 草地一侧的描边
        outer = dilate4(rm) & ~rm & (cv.mat == M_GROUND) & (R.Up == 1)
        c[outer] = G[3]
    cv.mat[rm] = M_ROAD


# ================================================================== 水面
def paint_water(R):
    m, cv = R.m, R.cv
    wet = m.mask(WET)
    if not wet.any():
        R.water_mask = np.zeros((R.H, R.W), bool)
        return
    deep = m.mask('~')
    for x, y in m.cells('=B'):
        nb = [m.at(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        deep[y, x] = ('~' in nb) or ('_' not in nb)
    noise = value_noise(R.W, R.H, 7, R.seed + 21)
    sm = box_blur(box_blur(upscale(wet), 4), 4)
    wm = sm > 0.70 + (noise - 0.5) * 0.26
    wm &= upscale(wet) > 0.5
    wm = clean_mask(wm)
    noise2 = value_noise(R.W, R.H, 6, R.seed + 22)
    dsm = box_blur(box_blur(upscale(deep), 3), 3)
    dm = (dsm > 0.5 + (noise2 - 0.5) * 0.35) & wm
    R.water_mask = wm
    du = dist_dir(wm, 'u'); dd = dist_dir(wm, 'd')
    dl = dist_dir(wm, 'l'); dr = dist_dir(wm, 'r')
    c = cv.c
    ys, xs = np.nonzero(wm)
    duL = du[ys, xs].tolist(); ddL = dd[ys, xs].tolist()
    dlL = dl[ys, xs].tolist(); drL = dr[ys, xs].tolist()
    dmL = dm[ys, xs].tolist()
    nz = value_noise(R.W, R.H, 14, R.seed + 23)[ys, xs].tolist()
    f = R.frame
    for i in range(len(ys)):
        y = int(ys[i]); x = int(xs[i])
        u, d, l, r = duL[i], ddL[i], dlL[i], drL[i]
        deepp = dmL[i]
        if R.snow:
            dmin = min(u, d, l, r)
            icew = 3 + int(nz[i] * 3.99)
            if (not deepp) or dmin <= icew:
                # 冰面
                col = WA[5]
                if u == 1:
                    col = SN[2]
                elif u == 2:
                    col = SN[1]
                elif d == 1:
                    col = SN[4]
                elif l == 1 or r == 1:
                    col = SN[2]
                elif deepp and dmin == icew:
                    col = SN[4]    # 冰缘
                else:
                    hv = ih(x // 3, y // 2, R.seed + 31)
                    if hv % 19 == 0:
                        col = WA[4]
                    elif hv % 19 == 1:
                        col = SN[4]
            else:
                col = WA[2]
                if dmin == icew + 1:
                    col = WA[1]
                elif dmin == icew + 2:
                    col = WA[1] if u < d else WA[2]
            c[y, x] = col
            continue
        if deepp:
            col = WA[3]
            if u == 1:
                col = EA[2]
            elif u == 2:
                col = EA[1]
            elif u == 3:
                col = WA[1]
            elif d == 1:
                col = WA[5] if ((x + f * 3) // 3) % 4 else WA[4]
            elif u <= 5:
                col = WA[2]
            elif l == 1 or r == 1:
                col = WA[2]
            elif d == 2:
                col = WA[4]
        else:
            col = WA[4]
            if u == 1:
                col = EA[4]
            elif u == 2:
                col = WA[5]
            elif d == 1:
                col = WA[5]
            elif l == 1 or r == 1:
                col = WA[5]
            elif u == 3:
                col = WA[3]
        c[y, x] = col
    cv.mat[wm] = M_WATER
    # 岸边描边：北岸草缘加深，南岸草缘提亮
    top_lip = np.zeros_like(wm)
    top_lip[:-1] = (~wm[:-1]) & wm[1:] & (du[1:] == 1)
    bot_lip = np.zeros_like(wm)
    bot_lip[1:] = (~wm[1:]) & wm[:-1] & (dd[:-1] == 1)
    lipg = (cv.mat != M_WATER)
    if R.snow:
        c[top_lip & lipg] = SN[2]
        c[bot_lip & lipg] = SN[4]
    else:
        c[top_lip & lipg & (R.Up == 1)] = G[3]
        c[bot_lip & lipg & (R.Up == 1)] = G[5]
    side = np.zeros_like(wm)
    side[:, 1:] |= (~wm[:, 1:]) & wm[:, :-1]
    side[:, :-1] |= (~wm[:, :-1]) & wm[:, 1:]
    side &= lipg & ~top_lip & ~bot_lip & (R.Up == 1)
    c[side] = R.gd
    # 静态水纹 + 动画波光
    water_sparkles(R, wm, dm, du, dd, dl, dr)


def water_sparkles(R, wm, dm, du, dd, dl, dr):
    m, cv = R.m, R.cv
    f = R.frame
    for x, y in m.cells(WET):
        if m.g[y][x] in '=B':
            continue
        X, Y = x * TS, y * TS
        for k in range(3):
            hv = ih(x, y, R.seed, 90 + k)
            gx = X + 1 + hv % 11
            gy = Y + 2 + (hv >> 8) % 12
            if not (0 <= gx < R.W - 4 and 0 <= gy < R.H):
                continue
            if not all(wm[gy, gx + i] for i in range(4)):
                continue
            if du[gy, gx] < 6 or dd[gy, gx] < 3 or dl[gy, gx] < 2 or dr[gy, gx + 3] < 2:
                continue
            deepp = dm[gy, gx]
            if R.snow:
                dmin = min(du[gy, gx], dd[gy, gx], dl[gy, gx], dr[gy, gx + 3])
                if dmin <= 8 or not deepp:
                    # 冰面闪点
                    ph = (f + (hv >> 16)) % 3
                    if k == 0 and ph == 0:
                        cv.put(gx + 1, gy, SN[4], M_WATER)
                    continue
                lo, hi = WA[3], WA[4]
            else:
                lo, hi = (WA[4], WA[5]) if deepp else (WA[5], CW[4])
            if k == 2:
                # 静态波纹（︶ 形）
                c1 = WA[2] if deepp else WA[3]
                cv.put(gx, gy, c1, M_WATER)
                cv.put(gx + 1, gy + 1, c1, M_WATER)
                cv.put(gx + 2, gy + 1, c1, M_WATER)
                cv.put(gx + 3, gy, c1, M_WATER)
                continue
            R.anim_cells.add((x, y))
            ph = (f + (hv >> 16)) % 3
            if ph == 0:
                pts = [(0, lo), (1, lo)]
            elif ph == 1:
                pts = [(1, lo), (2, hi), (3, lo)]
            else:
                pts = [(2, lo)]
            for dx, col in pts:
                cv.put(gx + dx, gy, col, M_WATER)


# ================================================================== 悬崖
def paint_cliffs(R):
    """悬崖：上沿是上层地面的唇边；崖面是长短不一的竖向岩缕（受光的亮缕与背光的暗缝交错），
    偶尔一道横向岩棚；越往下越暗，底部有一线接地阴影。"""
    m, cv = R.m, R.cv
    cells = list(m.cells('x'))
    if not cells:
        return
    rk = ST if R.snow else RO
    hi = rk[5] if len(rk) > 5 else rk[4]
    shades = [rk[2], rk[3], rk[3], rk[4], rk[3], rk[2]]
    for x, y in cells:
        X, Y = x * TS, y * TS
        top_open = m.at(x, y - 1) != 'x'
        bot_open = m.at(x, y + 1) != 'x'
        lo = m.at(x - 1, y) != 'x' and x > 0
        ro = m.at(x + 1, y) != 'x' and x < m.w - 1
        lip = [2 + ih(X + px, 83) % 2 for px in range(TS)] if top_open else [0] * TS
        ledge_y = Y + 6 + ih(x, y, 88) % 5 if ih(x, y, 89) % 3 == 0 else -99
        for py in range(TS):
            gy = Y + py
            xl = 0
            xr = 15
            if lo:
                xl = 1 + (ih(gy // 3, x, 5) % 2) + (1 if py >= 12 and bot_open else 0)
            if ro:
                xr = 14 - (ih(gy // 3, x, 6) % 2) - (1 if py >= 12 and bot_open else 0)
            for px in range(xl, xr + 1):
                gx = X + px
                if top_open and py < lip[px]:
                    col = R.gb if py < lip[px] - 1 else R.gd
                elif top_open and py == lip[px]:
                    col = rk[0]
                elif bot_open and py == 15:
                    col = rk[0]
                else:
                    # 该列的分段：段长 3..9，段号决定色调
                    seg_off = ih(gx, R.seed, 91) % 9
                    seglen = 3 + ih(gx, R.seed, 92) % 7
                    seg = (gy + seg_off) // seglen
                    pos = (gy + seg_off) % seglen
                    col = shades[ih(gx, seg, R.seed, 93) % len(shades)]
                    if pos == 0:
                        col = rk[1]                    # 岩缕之间的暗缝
                    elif pos == 1 and col == rk[4]:
                        col = hi
                    # 相邻列之间偶尔一条竖向深缝
                    if ih(gx, seg, 94) % 7 == 0:
                        col = rk[1]
                    if gy == ledge_y:
                        col = rk[1]
                    elif gy == ledge_y + 1:
                        col = SN[4] if R.snow else hi
                    elif gy == ledge_y + 2 and R.snow and ih(gx, 95) % 2:
                        col = SN[3]
                    if top_open and py == lip[px] + 1:
                        col = rk[1]
                    elif top_open and py == lip[px] + 2 and col in (rk[3], rk[4]):
                        col = hi
                    if bot_open and py >= 11:
                        col = shade(col, -1)
                        if py == 14:
                            col = rk[1]
                if px == xl and lo:
                    col = rk[0]
                elif px == xr and ro:
                    col = rk[0]
                elif px == xl + 1 and lo and col not in (rk[0],) and not (top_open and py <= lip[px]):
                    col = rk[4]
                elif px == xr - 1 and ro and col not in (rk[0],) and not (top_open and py <= lip[px]):
                    col = rk[1]
                cv.put(gx, gy, col, M_WALL)
        if bot_open:
            for px in range(xl if lo else 0, (xr if ro else 15) + 1):
                cv.darken(X + px, Y + 16, 1)


# ================================================================== 山体底色
def paint_mountain_bg(R):
    m, cv = R.m, R.cv
    mm = m.mask(MOUNT)
    if not mm.any():
        return
    # 相邻的山格之间填上山坡，避免峰与峰之间露出草地
    base = np.zeros((R.H, R.W), bool)
    for x, y in m.cells(MOUNT):
        X, Y = x * TS, y * TS
        up = m.at(x, y - 1) in MOUNT
        y0 = Y if up else Y + 8
        base[y0:Y + TS, X + 2:X + TS - 2] = True
        if m.at(x - 1, y) in MOUNT:
            base[Y + (0 if up and m.at(x - 1, y - 1) in MOUNT else 8):Y + TS, X:X + 3] = True
        if m.at(x + 1, y) in MOUNT:
            base[Y + (0 if up and m.at(x + 1, y - 1) in MOUNT else 8):Y + TS, X + TS - 3:X + TS] = True
    sm = box_blur(box_blur(base, 2), 2)
    bm = (sm > 0.5) & base
    c = cv.c
    yy, xx = np.mgrid[0:R.H, 0:R.W]
    hh = nh(xx // 3, yy // 5, R.seed + 42)
    if R.snow:
        c[bm] = ST[2]
        c[bm & ((hh % 5) == 0)] = ST[1]
        c[bm & ((hh % 5) == 1)] = SN[2]
    else:
        c[bm] = RO[2]
        c[bm & ((hh % 5) == 0)] = RO[1]
        c[bm & ((hh % 5) == 1)] = RO[3]
    edge = bm & ~erode4(bm)
    c[edge] = (ST[0] if R.snow else RO[0])
    cv.mat[bm] = M_WALL


# ================================================================== 墙体
def wall_face(m, x, y):
    ch = m.at(x, y)
    if ch in 'DG':
        return True
    return ch == '#' and m.at(x, y + 1) not in WALLS


def wall_depth(m):
    INF = 99
    d = [[0 if m.g[y][x] not in WALLS else INF for x in range(m.w)] for y in range(m.h)]
    changed = True
    while changed:
        changed = False
        for y in range(m.h):
            for x in range(m.w):
                if d[y][x] == 0:
                    continue
                best = d[y][x]
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if m.inb(nx, ny):
                            best = min(best, d[ny][nx] + 1)
                if best < d[y][x]:
                    d[y][x] = best
                    changed = True
    return d


def wall_style(R):
    if R.th == 'indoor':
        return dict(r=ST, top=1, deep=0, merlon=False, kind='monastery')
    if R.th == 'castle':
        return dict(r=RO, top=2, deep=1, merlon=True, kind='castle')
    return dict(r=ST, top=2, deep=1, merlon=True, kind='fort')


def paint_walls(R):
    m, cv = R.m, R.cv
    if not any(ch in WALLS for row in m.g for ch in row):
        return
    st = wall_style(R)
    r = st['r']
    depth = wall_depth(m)
    part = np.zeros((R.H, R.W), np.uint8)
    deep = np.zeros((R.H, R.W), bool)
    outdoor_top = np.zeros((R.H, R.W), bool)
    merl = np.zeros((R.H, R.W), bool)
    for x, y in m.cells(WALLS):
        X, Y = x * TS, y * TS
        od = any(R.is_outdoor(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
        if wall_face(m, x, y):
            part[Y:Y + 6, X:X + TS] = 1
            part[Y + 6:Y + TS, X:X + TS] = 2
            if st['merlon'] and R.is_outdoor(x, y + 1) and m.at(x, y) == '#':
                merl[Y:Y + 6, X:X + TS] = True
        else:
            part[Y:Y + TS, X:X + TS] = 1
        if depth[y][x] >= 2:
            deep[Y:Y + TS, X:X + TS] = True
        if od and st['kind'] != 'monastery':
            outdoor_top[Y:Y + TS, X:X + TS] = True
    top = part == 1
    face = part == 2
    tu = dist_dir(top, 'u'); td = dist_dir(top, 'd')
    tl = dist_dir(top, 'l'); tr = dist_dir(top, 'r')
    fl = dist_dir(face, 'l'); frr = dist_dir(face, 'r')
    c = cv.c
    yy, xx = np.mgrid[0:R.H, 0:R.W]
    # ---- 顶面
    row = yy // 8
    off = (row % 2) * 8
    seam = ((yy % 8) == 0) | (((xx + off) % 16) == 0)
    tb = st['top']
    lv = np.full((R.H, R.W), tb)
    lv[seam] = tb - 1
    lv[deep & ~outdoor_top] = st['deep']
    lv[deep & ~outdoor_top & seam] = max(0, st['deep'] - 1)
    if st['kind'] == 'monastery':
        lv[deep & seam] = 0
    lv[outdoor_top & ~seam] = tb
    below = np.zeros((R.H, R.W), np.uint8)
    below[:-1] = part[1:]
    below[-1] = part[-1]
    lv[(tu == 2)] = 3
    lv[(tl == 2)] = 3
    lv[(tr == 2)] = tb - 1 if tb > 1 else 1
    lv[(td == 2) & (below != 0)] = 3
    lv[(td == 1) & (below == 2)] = 4
    lv[(tu == 1) | (tl == 1) | (tr == 1)] = 0
    lv[(td == 1) & (below == 0)] = 0
    topc = lv_colors(lv, r, R.H, R.W)
    c[top] = topc[top]
    if R.snow:
        # 墙顶积雪：北沿内侧一道雪棱 + 稀疏雪块，保留石面让墙体清楚可辨
        hh2 = nh(xx // 3, yy // 2, R.seed + 61)
        rim = top & ((tu == 2) | (tu == 3)) & (tl > 1) & (tr > 1)
        c[rim & (tu == 2)] = SN[4]
        c[rim & (tu == 3)] = SN[3]
        fleck = top & (tu > 4) & (tl > 2) & (tr > 2) & (td > 2) & ((hh2 % 11) == 0)
        c[fleck] = SN[3]
        fleck2 = np.zeros_like(fleck)
        fleck2[:, 1:] = fleck[:, :-1]
        fleck2 &= top & (tr > 1)
        c[fleck2] = SN[4]
        # 前沿唇口上的一线积雪
        lipm = top & (td == 1) & (below == 2)
        c[lipm] = SN[4]
    # ---- 垛口（外墙正面上沿）
    if merl.any():
        for y0 in range(0, R.H, TS):
            for x0 in range(0, R.W, TS):
                if not merl[y0, x0]:
                    continue
                for px in range(TS):
                    gx = x0 + px
                    k = gx % 5
                    ismer = k in (0, 1, 2)
                    for py in range(1, 6):
                        gy = y0 + py
                        if tl[gy, gx] == 1 or tr[gy, gx] == 1:
                            continue
                        if ismer:
                            if py == 1:
                                col = r[0]
                            elif py == 2:
                                col = SN[4] if R.snow else r[5 if len(r) > 5 else 4]
                            elif py == 5:
                                col = r[4]
                            else:
                                col = r[4] if k == 0 else (r[3] if k == 1 else r[2])
                        else:
                            if py <= 2:
                                continue
                            col = r[1] if py < 5 else r[4]
                            if py == 3:
                                col = r[0]
                        cv.put(gx, gy, col, M_WALL)
    # ---- 正面
    ccy = yy % TS
    if st['kind'] == 'monastery':
        course = np.where(ccy >= 10, 1, 0)
        coff = np.where(course == 1, 4, 0)
        bx = (xx + coff) % 8
        flv = np.full((R.H, R.W), 3)
        flv[bx == 1] = 4
        flv[bx == 7] = 2
        flv[bx == 0] = 1
        flv[(ccy == 10)] = 1
        flv[(ccy == 7) & (bx != 0)] = 4
        flv[(ccy == 11) & (bx != 0)] = 4
        flv[ccy == 6] = 2
        flv[ccy == 14] = 2
        flv[ccy == 15] = 1
        hh = nh((xx + coff) // 8, yy // 4, R.seed + 71)
        flv[((hh % 7) == 0) & (flv == 3)] = 2
        flv = np.where(flv >= 2, flv - 1, flv)
    else:
        course = np.where(ccy >= 11, 1, 0)
        coff = np.where(course == 1, 5, 0)
        bx = (xx + coff) % 10
        flv = np.full((R.H, R.W), 3)
        flv[bx == 1] = 4
        flv[bx == 9] = 2
        flv[bx == 0] = 1
        flv[ccy == 11] = 1
        flv[(ccy == 7) & (bx != 0)] = 4
        flv[(ccy == 12) & (bx != 0)] = 4
        flv[ccy == 6] = 1
        flv[ccy == 15] = 1
        hh = nh((xx + coff) // 10, yy // 5, R.seed + 72)
        flv[((hh % 6) == 0) & (flv == 3)] = 2
    flv[fl == 2] = 4
    flv[frr == 2] = 1
    flv[(fl == 1) | (frr == 1)] = 0
    facec = lv_colors(flv, r, R.H, R.W)
    c[face] = facec[face]
    cv.mat[part > 0] = M_WALL
    R.wall_part = part
    # 墙脚阴影
    sh = np.zeros((R.H, R.W), bool)
    sh[1:] = (part[:-1] == 2) & (part[1:] == 0)
    for gy, gx in zip(*np.nonzero(sh)):
        cv.darken(int(gx), int(gy), 1)
    # ---- 装饰：火把、旗帜、箭窗
    wall_decor(R, st)


TORCH_FLAMES = [
    ['..a..',
     '.aba.',
     '.bcb.',
     '.bcb.',
     '..b..'],
    ['.a...',
     '.ab..',
     '.bcb.',
     'abcb.',
     '..b..'],
    ['...a.',
     '..ba.',
     '.bcb.',
     '.bcba',
     '..b..'],
]


def draw_torch(R, gx, gy, x, y):
    """gx,gy = 火焰底部中心。火焰整体落在所在格内。"""
    cv = R.cv
    # 铁托架
    cv.put(gx - 1, gy + 1, IR[1], M_WALL)
    cv.put(gx, gy + 1, IR[3], M_WALL)
    cv.put(gx + 1, gy + 1, IR[1], M_WALL)
    cv.put(gx, gy + 2, IR[2], M_WALL)
    cv.put(gx, gy + 3, IR[1], M_WALL)
    cv.put(gx - 1, gy, WO[1], M_WALL)
    cv.put(gx, gy, WO[2], M_WALL)
    cv.put(gx + 1, gy, WO[1], M_WALL)
    # 墙面暖光（静态，用亮一级的墙色）
    for dy in range(-6, 4):
        for dx in range(-3, 4):
            if dx * dx + (dy + 2) * (dy + 2) * 0.6 <= 7 and not (abs(dx) <= 1 and -5 <= dy <= 0):
                px, py = gx + dx, gy + dy
                if R.cv.mat[py, px] == M_WALL if (0 <= px < R.W and 0 <= py < R.H) else False:
                    col = cv.get(px, py)
                    cv.put(px, py, shade(col, 1), M_WALL)
    fl = TORCH_FLAMES[R.frame % 3]
    leg = {'a': FI[1], 'b': FI[2], 'c': FI[3]}
    blit(cv, sprite(fl, leg), gx - 2, gy - 5, M_WALL)
    R.anim_cells.add((x, y))


def draw_banner(R, X, Y):
    """城堡室内墙面的垂幡（静态）。X,Y 为格左上角。"""
    cv = R.cv
    x0, x1 = X + 5, X + 10
    for py in range(6, 15):
        for px in range(x0, x1 + 1):
            if py == 14 and px in (x0 + 2, x0 + 3):
                continue
            if py == 13 and px in (x0 + 2, x0 + 3):
                col = CR[2]
            elif px == x0 or px == x1:
                col = GO[2] if px == x1 else GO[3]
            elif py == 6:
                col = GO[4]
            else:
                col = CR[3] if px < x1 - 1 else CR[2]
            cv.put(px, Y + py, col, M_WALL)
    # 白鹿徽记（简化成鹿角+鹿头）
    for dx, dy, col in ((1, 9, CW[4]), (4, 9, CW[4]), (1, 8, CW[3]), (4, 8, CW[3]),
                        (2, 10, CW[4]), (3, 10, CW[4]), (2, 11, CW[3]), (3, 11, CW[3])):
        cv.put(x0 + dx, Y + dy, col, M_WALL)
    # 挂杆
    for px in range(x0 - 1, x1 + 2):
        cv.put(px, Y + 6, WO[1] if px in (x0 - 1, x1 + 1) else GO[3], M_WALL)


def wall_decor(R, st):
    m = R.m
    runs = []
    for y in range(m.h):
        x = 0
        while x < m.w:
            if m.g[y][x] == '#' and wall_face(m, x, y):
                x0 = x
                while x < m.w and m.g[y][x] in WALLS and wall_face(m, x, y):
                    x += 1
                runs.append((y, x0, x - 1))
            else:
                x += 1
    for y, x0, x1 in runs:
        for x in range(x0, x1 + 1):
            if m.g[y][x] != '#':
                continue
            below = m.at(x, y + 1)
            if y + 1 >= m.h or below in WET or below in 'x':
                continue
            X, Y = x * TS, y * TS
            k = x - x0
            n = x1 - x0 + 1
            indoor_face = not R.is_outdoor(x, y + 1)
            if indoor_face:
                if n >= 3 and k % 4 == 1 and x != x1 and m.at(x + 1, y) != 'D' and m.at(x - 1, y) != 'D':
                    draw_torch(R, X + 8, Y + 9, x, y)
                elif st['kind'] == 'castle' and n >= 5 and k % 4 == 3 and x != x1 and \
                        m.at(x + 1, y) not in 'DG' and m.at(x - 1, y) not in 'DG':
                    draw_banner(R, X, Y)
            else:
                # 外墙箭窗
                if k % 3 == 1 and m.at(x + 1, y) not in 'DG' and m.at(x - 1, y) not in 'DG':
                    cv = R.cv
                    r = st['r']
                    for py in range(8, 12):
                        cv.put(X + 7, Y + py, INK2, M_WALL)
                        cv.put(X + 8, Y + py, r[1], M_WALL)
                    cv.put(X + 7, Y + 12, r[4], M_WALL)
                    cv.put(X + 8, Y + 12, r[4], M_WALL)


# ================================================================== 桥
def bridge_components(R):
    m = R.m
    comps = components(m, '=B')
    stone_set = set(tuple(p) for p in m.art.get('stone_bridges', []))
    wood_set = set(tuple(p) for p in m.art.get('wood_bridges', []))
    glob_style = m.art.get('bridge')
    out = []
    for comp in comps:
        xs = [p[0] for p in comp]
        ys = [p[1] for p in comp]
        w = max(xs) - min(xs) + 1
        h = max(ys) - min(ys) + 1
        if w > h:
            horiz = True
        elif h > w:
            horiz = False
        else:
            x, y = comp[0]

            def wetc(ch):
                return ch in '~_'
            sh = (not wetc(m.at(x - 1, y))) + (not wetc(m.at(x + 1, y))) + wetc(m.at(x, y - 1)) + wetc(m.at(x, y + 1))
            sv = (not wetc(m.at(x, y - 1))) + (not wetc(m.at(x, y + 1))) + wetc(m.at(x - 1, y)) + wetc(m.at(x + 1, y))
            horiz = sh >= sv
        style = 'stone' if (any(m.g[y][x] == 'B' for x, y in comp) or R.th == 'castle') else 'wood'
        if glob_style in ('stone', 'wood'):
            style = glob_style
        if any(p in stone_set for p in comp):
            style = 'stone'
        if any(p in wood_set for p in comp):
            style = 'wood'
        out.append((comp, horiz, style))
    return out


def paint_bridges(R):
    m = R.m
    for comp, horiz, style in bridge_components(R):
        for x, y in comp:
            broken = m.g[y][x] == 'B'
            if horiz:
                a = m.at(x - 1, y)
                b = m.at(x + 1, y)
            else:
                a = m.at(x, y - 1)
                b = m.at(x, y + 1)
            ca = a not in '~_B'   # 该侧有桥面/陆地相连
            cb = b not in '~_B'
            draw_bridge_cell(R, x, y, horiz, style, broken, ca, cb)


def draw_bridge_cell(R, x, y, horiz, style, broken, ca, cb):
    cv = R.cv
    X, Y = x * TS, y * TS
    snow = R.snow
    # 断口：沿桥向的像素坐标 t（0..15），保留范围
    keep = None
    if broken:
        def jag(i, s):
            return ih(x, y, i, s) % 3
        if ca and cb:
            keep = lambda t, s: t <= 4 + jag(s, 1) or t >= 11 - jag(s, 2)  # noqa: E731
        elif ca:
            keep = lambda t, s: t <= 6 + jag(s, 1)  # noqa: E731
        elif cb:
            keep = lambda t, s: t >= 9 - jag(s, 2)  # noqa: E731
        else:
            keep = lambda t, s: False  # noqa: E731

    def P(px, py, col):
        # px,py 是格内坐标；t 沿桥向，s 横向
        if keep is not None:
            t, s = (px, py) if horiz else (py, px)
            if not keep(t, s):
                return
        cv.put(X + px, Y + py, col, M_BRIDGE)

    if style == 'wood':
        if horiz:
            for px in range(16):
                # 水面阴影
                P(px, 15, WA[1] if not snow else WA[3])
                for py in range(3, 13):
                    k = px % 3
                    col = WO[1] if k == 0 else (WO[4] if k == 1 else WO[3])
                    if py == 3:
                        col = WO[2] if k else WO[1]
                    if py == 12:
                        col = WO[1]
                    if ih(px // 3, x, y, 3) % 5 == 0 and k and 5 <= py <= 10:
                        col = WO[2]
                    P(px, py, col)
                # 远侧栏杆
                P(px, 1, WO[0])
                P(px, 2, SN[4] if snow else WO[3])
                # 近侧栏杆
                P(px, 11, SN[4] if snow else WO[4])
                P(px, 12, WO[2])
                P(px, 13, WO[1])
                P(px, 14, WO[0])
            for px in (1, 9):
                for py, col in ((0, WO[0]), (1, WO[3]), (2, WO[2]), (3, WO[1])):
                    P(px, py, col)
                    P(px + 1, py, WO[0] if py == 0 else WO[1])
                for py, col in ((9, WO[0]), (10, WO[4]), (11, WO[3]), (12, WO[2]), (13, WO[1]), (14, WO[0])):
                    P(px, py, col)
                    P(px + 1, py, WO[0] if py in (9, 14) else WO[1])
                if snow:
                    P(px, 0, SN[4]); P(px + 1, 0, SN[3])
                    P(px, 9, SN[4]); P(px + 1, 9, SN[3])
        else:
            for py in range(16):
                P(14, py, WA[1] if not snow else WA[3])
                P(15, py, WA[2] if not snow else WA[4])
                for px in range(3, 13):
                    k = py % 3
                    col = WO[1] if k == 0 else (WO[4] if k == 1 else WO[3])
                    if px == 3:
                        col = WO[3] if k else WO[1]
                    if px == 12:
                        col = WO[1]
                    if ih(py // 3, x, y, 4) % 5 == 0 and k and 5 <= px <= 10:
                        col = WO[2]
                    P(px, py, col)
                P(1, py, WO[0]); P(2, py, SN[4] if snow else WO[3]); P(3, py, WO[1])
                P(12, py, SN[4] if snow else WO[3]); P(13, py, WO[1]); P(14, py, WO[0])
            for py in (2, 10):
                for px, col in ((1, WO[0]), (2, WO[4]), (3, WO[2]), (4, WO[0])):
                    P(px, py, col); P(px, py + 1, WO[1] if px in (2, 3) else WO[0])
                for px, col in ((11, WO[0]), (12, WO[4]), (13, WO[2]), (14, WO[0])):
                    P(px, py, col); P(px, py + 1, WO[1] if px in (12, 13) else WO[0])
                if snow:
                    P(2, py - 1, SN[4]); P(3, py - 1, SN[3]); P(12, py - 1, SN[4]); P(13, py - 1, SN[3])
    else:
        rk = RO if not snow else ST
        if horiz:
            for px in range(16):
                P(px, 15, WA[1] if not snow else WA[3])
                for py in range(3, 12):
                    k = (px + (4 if (py // 3) % 2 else 0)) % 8
                    col = rk[3]
                    if py % 3 == 0 or k == 0:
                        col = rk[2]
                    elif py % 3 == 1 or k == 1:
                        col = rk[4]
                    P(px, py, col)
                # 远侧矮墙
                P(px, 0, rk[0]); P(px, 1, SN[4] if snow else rk[5 if len(rk) > 5 else 4]); P(px, 2, rk[2])
                # 近侧矮墙 + 桥身
                P(px, 11, rk[0]); P(px, 12, SN[4] if snow else rk[5 if len(rk) > 5 else 4])
                P(px, 13, rk[3] if px % 8 else rk[1]); P(px, 14, rk[2] if px % 8 else rk[1])
            for px in range(16):
                if ((X + px) % 32) in range(10, 22):
                    P(px, 14, rk[0] if ((X + px) % 32) in (10, 21) else INK2)
        else:
            for py in range(16):
                P(14, py, WA[1] if not snow else WA[3])
                P(15, py, WA[2] if not snow else WA[4])
                for px in range(3, 13):
                    k = (py + (4 if (px // 3) % 2 else 0)) % 8
                    col = rk[3]
                    if px % 3 == 0 or k == 0:
                        col = rk[2]
                    elif px % 3 == 1 or k == 1:
                        col = rk[4]
                    P(px, py, col)
                P(0, py, rk[0]); P(1, py, SN[4] if snow else rk[4]); P(2, py, rk[2]); P(3, py, rk[1])
                P(12, py, rk[1]); P(13, py, SN[4] if snow else rk[4]); P(14, py, rk[2]); P(15, py, rk[0])
    if broken:
        # 断口处的碎木/碎石与浪花
        for i in range(3):
            hv = ih(x, y, 200 + i)
            if horiz:
                bx = X + 5 + hv % 6
                by = Y + 4 + (hv >> 8) % 8
            else:
                bx = X + 4 + (hv >> 8) % 8
                by = Y + 5 + hv % 6
            if R.water_mask[by, bx]:
                if style == 'wood':
                    cv.put(bx, by, WO[2], M_WATER); cv.put(bx + 1, by, WO[3], M_WATER); cv.put(bx + 2, by, WO[1], M_WATER)
                    cv.put(bx, by + 1, WA[5], M_WATER); cv.put(bx + 1, by + 1, WA[5], M_WATER)
                else:
                    rk = RO if not snow else ST
                    cv.put(bx, by, rk[4], M_WATER); cv.put(bx + 1, by, rk[3], M_WATER)
                    cv.put(bx, by + 1, rk[2], M_WATER); cv.put(bx + 1, by + 1, rk[1], M_WATER)
                    cv.put(bx - 1, by + 1, WA[5], M_WATER); cv.put(bx + 2, by + 1, WA[5], M_WATER)


# ================================================================== 楼梯（平面物件）
def paint_stairs(R):
    m, cv = R.m, R.cv
    for x, y in m.cells('S'):
        X, Y = x * TS, y * TS
        indoor = R.under[y][x] != 'ground'
        rk = ST if (indoor or R.snow) else RO
        # 外框
        for py in range(16):
            for px in range(1, 15):
                if px in (1, 14):
                    col = rk[0]
                elif px == 2:
                    col = rk[4]
                elif px == 13:
                    col = rk[2]
                elif py == 0 or py == 15:
                    col = rk[0]
                else:
                    # 台阶：越往下越暗
                    step = (py - 1) // 3
                    k = (py - 1) % 3
                    ramp_idx = max(0, 4 - step)
                    if k == 0:
                        col = rk[min(len(rk) - 1, ramp_idx + 1)] if step < 4 else INK2
                    elif k == 1:
                        col = rk[ramp_idx] if step < 4 else INK2
                    else:
                        col = rk[max(0, ramp_idx - 2)] if step < 3 else INK
                    if px == 3 and step < 4:
                        col = shade(col, -1)
                    if px == 12 and step < 4:
                        col = shade(col, -1)
                if px in (2, 13) and R.snow and py < 3:
                    col = SN[4]
                cv.put(X + px, Y + py, col, M_OBJ)


# ================================================================== 物件：树
_canopy_cache = {}


TREE_COLS = [FO[0], FO[1], FO[2], FO[3], FO[4], G[3], G[4]]


def _disc(cx, cy, r):
    out = []
    for y in range(int(math.floor(cy - r)) - 1, int(math.ceil(cy + r)) + 1):
        for x in range(int(math.floor(cx - r)) - 1, int(math.ceil(cx + r)) + 1):
            if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r * r:
                out.append((x, y))
    return out


def canopy(r, seed):
    """“叠团”式树冠：由后往前一团一团盖上去，每团画成 暗→中→亮→高光 的偏心同心圆，
    形成干净的月牙受光（左上亮）。返回 {(dx,dy): 级别}，0=描边，1..6 见 TREE_COLS。"""
    key = (int(r * 4), seed % 48)
    if key in _canopy_cache:
        return _canopy_cache[key]
    rng = random.Random(key[1] * 7919 + key[0] * 31)
    # 叶簇：六角网格上的小圆团（半径约 2.2），给整体球面光加上“扇贝形”的明暗边界
    sp = 3.0
    ox0, oy0 = rng.uniform(0, sp), rng.uniform(0, sp)
    cl = []
    for iy in range(-6, 7):
        for ix in range(-6, 7):
            cx = ix * sp + (sp / 2 if iy % 2 else 0) + ox0 - sp
            cy = iy * sp * 0.85 + oy0 - sp
            cl.append((cx + rng.uniform(-0.4, 0.4), cy + rng.uniform(-0.4, 0.4)))
    L = (-0.62, -0.72, 0.55)
    ln = math.sqrt(sum(v * v for v in L))
    L = tuple(v / ln for v in L)
    R_ = int(r + 2)
    pix = {}
    for dy in range(-R_, R_ + 1):
        for dx in range(-R_, R_ + 1):
            px, py = dx + 0.5, dy + 0.5
            best = None
            bd = 99.0
            for (cx, cy) in cl:
                d2 = (px - cx) ** 2 + (py - cy) ** 2
                if d2 < bd:
                    bd = d2
                    best = (cx, cy)
            bx, by = (px - best[0]) / 2.2, (py - best[1]) / 2.2
            bump = -(bx * 0.75 + by * 0.9)
            # 轮廓：球 + 叶簇起伏
            rr = r + 0.55 * max(-1.0, min(1.0, 1.0 - math.sqrt(bd) / 1.6))
            dist = math.sqrt(px * px + (py * 1.05) ** 2)
            if dist > rr:
                continue
            nx, ny = px / r, py / r
            nz = math.sqrt(max(0.0, 1 - min(1.0, nx * nx + ny * ny)))
            v = nx * L[0] + ny * L[1] + nz * L[2] + 0.30 * max(-1.0, min(1.0, bump))
            if v > 0.84:
                lv = 6
            elif v > 0.60:
                lv = 5
            elif v > 0.30:
                lv = 3
            elif v > -0.02:
                lv = 2
            else:
                lv = 1
            pix[(dx, dy)] = lv
    out = dict(pix)
    for (dx, dy) in pix:
        for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            k = (dx + ox, dy + oy)
            if k not in pix:
                out[k] = 0
    _canopy_cache[key] = out
    return out


def draw_tree(R, cx, cy, r, seed):
    cv = R.cv
    icx, icy = int(round(cx)), int(round(cy))
    ty0 = icy + int(r * 0.5)
    ty1 = icy + int(r) + 1
    for yy in range(ty0, ty1 + 1):
        cv.put(icx - 1, yy, WO[0])
        cv.put(icx, yy, WO[2])
        cv.put(icx + 1, yy, WO[1])
        cv.put(icx + 2, yy, WO[0])
    cv.put(icx, ty1 + 1, WO[0]); cv.put(icx + 1, ty1 + 1, WO[0])
    for (dx, dy), lv in canopy(r, seed).items():
        cv.put(icx + dx, icy + dy, TREE_COLS[lv])


def draw_pine(R, cx, by, h, hw, seed, snow):
    """雪松：cx 中心，by 树冠底，h 树冠高，hw 底部半宽。"""
    cv = R.cv
    for yy in range(by, by + 3):
        cv.put(cx - 1, yy, WO[0]); cv.put(cx, yy, WO[2]); cv.put(cx + 1, yy, WO[1]); cv.put(cx + 2, yy, WO[0])
    top = by - h
    tiers = 3 if h < 13 else 4
    rng = random.Random(seed)
    for i in range(tiers):
        ty0 = top + int(i * h / (tiers + 0.5))
        ty1 = top + int((i + 1) * h / tiers)
        whw = hw * (0.42 + 0.58 * (i + 1) / tiers)
        span = max(1, ty1 - ty0)
        for yy in range(ty0, ty1 + 1):
            t = (yy - ty0) / span
            half = 0.6 + whw * t
            xl = int(round(cx + 0.5 - half))
            xr = int(round(cx + 0.5 + half)) - 1
            for xx in range(xl, xr + 1):
                rel = (xx - (cx + 0.5)) / max(0.5, half)
                if rel < -0.35:
                    col = FO[3]
                elif rel < 0.25:
                    col = FO[2]
                else:
                    col = FO[1]
                if yy == ty1:
                    col = FO[0] if (xx + i) % 2 == 0 else FO[1]
                if snow:
                    sd = yy - ty0
                    if sd <= 1 and rel < 0.5:
                        col = SN[4] if rel < 0 else SN[3]
                    elif sd == 2 and rel < -0.2 and (xx + yy) % 2 == 0:
                        col = SN[3]
                    elif yy == ty1 - 1 and rel < 0.1 and rng.random() < 0.4:
                        col = SN[4]
                cv.put(xx, yy, col)
            cv.put(xl - 1, yy, FO[0])
            cv.put(xr + 1, yy, FO[0])
        if ty0 == top:
            cv.put(cx, top - 1, FO[0]); cv.put(cx + 1, top - 1, FO[0])
            if snow:
                cv.put(cx, top, SN[4])


FOREST_LAYOUTS = [
    [(8, 5.0, 6.6)],
    [(4.5, 3.0, 4.6), (11.0, 6.5, 5.4)],
    [(11.5, 3.0, 4.6), (5.0, 6.5, 5.4)],
    [(4.0, 2.5, 4.2), (12.0, 2.0, 4.2), (8.0, 7.5, 5.2)],
]


def job_forest(R, x, y):
    X, Y = x * TS, y * TS
    cv = R.cv
    k = ih(x, y, R.seed, 300) % 4
    if R.snow:
        lay = [
            [(8, 13, 14, 6)],
            [(4, 11, 11, 4), (11, 14, 13, 5)],
            [(12, 11, 11, 4), (5, 14, 13, 5)],
            [(3, 10, 9, 3), (12, 10, 10, 4), (7, 14, 12, 5)],
        ][k]
        for i, (px, by, h, hw) in enumerate(lay):
            # 阴影
            for dy in range(0, 3):
                for dx in range(-hw, hw + 2):
                    cv.darken(X + px + dx + 2, Y + by + 1 + dy, 1)
        for i, (px, by, h, hw) in enumerate(lay):
            jx = ih(x, y, i, 301) % 3 - 1
            draw_pine(R, X + px + jx, Y + by, h, hw, ih(x, y, i), True)
        return
    lay = FOREST_LAYOUTS[k]
    for i, (px, py, r) in enumerate(lay):
        cxp = X + px + 2
        cyp = Y + py + r * 0.8
        for dy in range(-3, 4):
            for dx in range(-int(r) - 1, int(r) + 2):
                if (dx / (r + 1)) ** 2 + (dy / 2.6) ** 2 <= 1:
                    cv.darken(int(cxp + dx), int(cyp + dy), 1)
    for i, (px, py, r) in enumerate(lay):
        jx = (ih(x, y, i, 302) % 3 - 1) * 0.6
        jy = (ih(x, y, i, 303) % 3 - 1) * 0.5
        draw_tree(R, X + px + jx, Y + py + jy, r, ih(x, y, i, R.seed))


# ================================================================== 物件：丘陵
def draw_mound(R, cx, by, hw, hh, seed, dim=0):
    """钟形土丘：只在上缘描边，底部融进地面；左坡受光、右坡背光，顶部一道高光。"""
    cv = R.cv
    if R.snow:
        o, hi, lit, mid, sh, sh2 = ST[2], SN[4], SN[3], SN[2], SN[1], ST[2]
    else:
        o, hi, lit, mid, sh, sh2 = G[1], G[5], G[4], G[3], G[2], G[1]
    rng = random.Random(seed)
    crest = cx - hw * 0.08
    tops = {}
    for xx in range(int(math.floor(cx - hw)), int(math.ceil(cx + hw)) + 1):
        u = (xx + 0.5 - cx) / hw
        if abs(u) >= 1:
            continue
        tops[xx] = by - hh * (1 - u * u) ** 1.35
    L = (-0.62, 0.52, 0.58)
    for xx, top in tops.items():
        yt = int(math.ceil(top))
        for yy in range(yt, by + 1):
            u = (xx + 0.5 - crest) / hw
            w = (by - yy + 0.5) / hh
            nz = math.sqrt(max(0.0, 1 - min(1.0, u * u + w * w)))
            v = u * L[0] + w * L[1] + nz * L[2]
            if yy == yt:
                col = o
            elif v > 0.74:
                col = hi
            elif v > 0.44:
                col = lit
            elif v > 0.14:
                col = mid
            elif v > -0.12:
                col = sh
            else:
                col = sh2
            if dim and col not in (o,):
                col = shade(col, -1)
            cv.put(xx, yy, col, M_OBJ)
        # 两侧陡处的描边补一格，避免锯齿
        if xx - 1 in tops and tops[xx - 1] > top + 1:
            for yy in range(yt, int(math.ceil(tops[xx - 1]))):
                cv.put(xx, yy, o, M_OBJ)
        if xx + 1 in tops and tops[xx + 1] > top + 1:
            for yy in range(yt, int(math.ceil(tops[xx + 1]))):
                cv.put(xx, yy, o, M_OBJ)
    # 草丛/小石
    for k in range(2):
        tx = int(cx + rng.uniform(-hw * 0.55, hw * 0.3))
        if tx not in tops:
            continue
        ty = int(math.ceil(tops[tx])) + 3 + rng.randint(0, 3)
        if ty > by - 2:
            continue
        if R.snow:
            cv.put(tx, ty, ST[3], M_OBJ); cv.put(tx + 1, ty, ST[2], M_OBJ)
        else:
            cv.put(tx, ty, G[3], M_OBJ); cv.put(tx + 2, ty, G[3], M_OBJ); cv.put(tx + 1, ty + 1, G[3], M_OBJ)


def job_hill(R, x, y):
    X, Y = x * TS, y * TS
    k = ih(x, y, R.seed, 400) % 3
    if k == 0:
        draw_mound(R, X + 8, Y + 15, 11, 12, ih(x, y, 1))
    elif k == 1:
        draw_mound(R, X + 4, Y + 11, 7, 8, ih(x, y, 2), dim=0)
        draw_mound(R, X + 10, Y + 15, 9, 10, ih(x, y, 3))
    else:
        draw_mound(R, X + 12, Y + 11, 7, 8, ih(x, y, 4), dim=0)
        draw_mound(R, X + 6, Y + 15, 9, 10, ih(x, y, 5))


# ================================================================== 物件：山峰
def draw_peak(R, cx, ay, by, hwl, hwr, snowh, seed, dim=0, foot=False):
    """一座山峰：左侧受光面 + 右侧背光面，少量断续岩纹，锯齿状轮廓；snowh>0 时顶部积雪。
    雪地主题整体覆雪、背光面露岩。dim=1 时整体暗一级（后排小峰）。"""
    cv = R.cv
    snowy = R.snow
    rk = ST if snowy else RO
    rng = random.Random(seed)
    Hh = by - ay
    left, right, ridge = [], [], []
    jl = jr = jg = 0.0
    for i in range(Hh + 1):
        t = i / Hh
        prof = t ** 0.68
        if i % 2 == 0 and i > 1:
            jl = max(-1.2, min(1.2, jl + rng.choice((-1, 0, 0, 1)) * 0.8))
            jr = max(-1.2, min(1.2, jr + rng.choice((-1, 0, 0, 1)) * 0.8))
            jg = max(-1.0, min(1.0, jg + rng.choice((-1, 0, 1)) * 0.6))
        left.append(cx - hwl * prof + jl * min(1.0, t * 2.5))
        right.append(cx + hwr * prof + jr * min(1.0, t * 2.5))
        ridge.append(cx + 0.4 + hwr * 0.28 * t + jg * min(1.0, t * 2))
    snowline = {}

    def sline(xx):
        if xx not in snowline:
            v = snowh + (ih(xx, seed, 5) % 3) - 1
            if ih(xx // 2, seed, 6) % 3 == 0:
                v += 2
            snowline[xx] = v
        return snowline[xx]

    # 断续岩纹：受光面自山脊向左下，背光面向右下
    marks = {}
    for k in range(2):
        i0 = int(Hh * rng.uniform(0.28, 0.62))
        ln_ = rng.randint(3, 6)
        slope = rng.uniform(1.0, 1.6)
        x0 = ridge[i0] - 1.5
        for d in range(ln_):
            ii = i0 + int(round(d * slope))
            if ii > Hh - 2:
                break
            xx = int(round(x0 - d))
            marks[(xx, ii)] = 'L'
            marks.setdefault((xx + 1, ii), 'Lh')
    i0 = int(Hh * rng.uniform(0.35, 0.6))
    for d in range(rng.randint(3, 5)):
        ii = i0 + int(round(d * 1.3))
        if ii > Hh - 2:
            break
        marks[(int(round(ridge[i0] + 2 + d)), ii)] = 'R'
    lit_top = rk[5] if len(rk) > 5 else rk[4]
    # 山脚（下方不是山）：底部两角收圆、底边参差并描边
    foot_bot = {}
    if foot:
        xl0, xr0 = int(round(left[Hh])), int(round(right[Hh]))
        for xx in range(xl0, xr0 + 1):
            e = min(xx - xl0, xr0 - xx)
            cut = 2 if e == 0 else (1 if e <= 2 else (ih(xx, seed, 17) % 3 == 0))
            foot_bot[xx] = by - int(cut)
    for i in range(Hh + 1):
        yy = ay + i
        xl = int(round(left[i]))
        xr = int(round(right[i]))
        xg = int(round(ridge[i]))
        t = i / Hh
        for xx in range(xl, xr + 1):
            if foot and xx in foot_bot and yy > foot_bot[xx]:
                continue
            mk = marks.get((xx, i))
            if xx == xl or xx == xr:
                col = rk[0]
            elif xx <= xg:
                dd = xg - xx
                col = rk[3]
                if dd <= 1 and t < 0.75:
                    col = lit_top if t < 0.4 else rk[4]
                elif dd <= 3 and t < 0.45:
                    col = rk[4]
                if mk == 'L':
                    col = rk[2]
                elif mk == 'Lh' and dd > 1:
                    col = rk[4]
                if xx == xl + 1 and t > 0.12:
                    col = rk[2]
            else:
                dd = xx - xg
                col = rk[2]
                if dd == 1 or xx >= xr - 2 or t > 0.86:
                    col = rk[1]
                if mk == 'R':
                    col = rk[1]
            if snowy and xx not in (xl, xr) and i > sline(xx) and xx <= xg and t < 0.8:
                # 雪山受光面的残雪斑
                if ih(xx // 2, i // 2, seed, 13) % 5 == 0 and col == rk[3]:
                    col = SN[3]
            if dim and col != rk[0]:
                col = shade(col, -1)
            if snowh > 0 and xx not in (xl, xr) and i <= sline(xx):
                if xx <= xg:
                    col = SN[4] if ((xg - xx) <= 2 or i < 3) else SN[3]
                    if i == sline(xx) and i > 2:
                        col = SN[2]
                else:
                    col = SN[2] if (xx - xg) > 1 else SN[1]
                    if xx >= xr - 1:
                        col = SN[1]
            if foot and xx in foot_bot and yy == foot_bot[xx] and xx not in (xl, xr):
                col = rk[0]
            cv.put(xx, yy, col, M_OBJ)
    cv.put(int(round(cx)), ay - 1, rk[0])
    cv.put(int(round(cx)) + 1, ay, rk[0])
    if foot:
        for xx, yb in foot_bot.items():
            cv.darken(xx + 1, yb + 1, 1)
    # 山脚灌木（平原）
    if not snowy and not dim:
        for k in range(2):
            hv = ih(seed, k, 9)
            if hv % 2:
                continue
            bx = int(left[-1] + 3 + (hv >> 3) % max(1, int(right[-1] - left[-1] - 7)))
            byy = by - 1
            for dx, dy, col in ((0, 0, G[2]), (1, 0, G[2]), (2, 0, G[1]), (0, -1, G[3]), (1, -1, G[3]),
                                (2, -1, G[2]), (1, -2, G[3]), (-1, 0, G[1]), (3, 0, G[1])):
                cv.put(bx + dx, byy + dy, col, M_OBJ)


def job_mountain(R, x, y):
    m = R.m
    X, Y = x * TS, y * TS
    ch = m.g[y][x]
    s = ih(x, y, R.seed, 500)
    jx = (s >> 3) % 5 - 2          # 峰顶左右错落
    jy = (s >> 6) % 3              # 高低错落
    jw = ((s >> 9) % 3) - 1
    sn = R.snow
    foot = m.at(x, y + 1) not in MOUNT
    if ch == 'A':
        side = -1 if s % 2 else 1
        draw_peak(R, X + 8 + side * 6, Y - 2, Y + 14, 7, 7, 4 if not sn else 7, s + 1, dim=1)
        draw_peak(R, X + 8 + jx, Y - 10 + jy, Y + 15, 12 + jw, 13 + jw, 9 if not sn else 15, s + 2, foot=foot)
    else:
        k = s % 3
        if k != 2:
            side = -1 if k == 0 else 1
            draw_peak(R, X + 8 + side * 7, Y + 1 + jy, Y + 13, 6, 6, 0 if not sn else 4, s + 3, dim=1)
        draw_peak(R, X + 8 + jx, Y - 3 + jy, Y + 15, 11 + jw, 12 + jw, 0 if not sn else 7, s + 4, foot=foot)


# ================================================================== 物件：房屋
def roof_ramp(kind, R):
    if kind == 'blue':
        return RB
    if kind == 'thatch':
        return [EA[0], EA[1], EA[2], EA[3], EA[4]]
    return RR


def draw_house(R, comp):
    m, cv = R.m, R.cv
    cells = set(comp)
    xs = sorted(set(p[0] for p in comp))
    # 屋顶样式
    kinds = ['red', 'blue', 'thatch', 'red']
    kind = kinds[ih(comp[0][0], comp[0][1], R.seed, 600) % 4]
    over = m.art.get('roofs') or {}
    for (cx, cy) in comp:
        k = over.get('%d,%d' % (cx, cy))
        if k:
            kind = k
    r = roof_ramp(kind, R)
    plaster = CW
    cols = {}
    for x in xs:
        ys = sorted(p[1] for p in comp if p[0] == x)
        cols[x] = (ys[0], ys[-1])
    xmin = min(xs)
    # 多行房屋墙高 10，单行房屋墙高 8
    tall = any(cols[x][1] > cols[x][0] for x in xs)
    wall_top = 5 if tall else 7      # 墙面起始（格内 y）
    # ---- 屋顶（四坡：上沿两角内收）
    for x in xs:
        yt, yb = cols[x]
        X = x * TS
        rt = yt * TS + (1 if tall else 0)
        re = yb * TS + wall_top - 1
        Hr = re - rt
        hip = 2 if Hr >= 10 else 1
        lin = (x - 1) in cols and cols[x - 1][1] == yb
        rin = (x + 1) in cols and cols[x + 1][1] == yb
        for px in range(TS):
            gx = X + px
            for gy in range(rt, re + 1):
                k = gy - rt
                ins = max(0, hip - k)
                if not lin and px < ins:
                    continue
                if not rin and px > 15 - ins:
                    continue
                edge_l = (not lin) and px == ins
                edge_r = (not rin) and px == 15 - ins
                if k == 0 or gy == re:
                    col = r[0]
                elif k == 1:
                    col = r[4]
                elif gy == re - 1:
                    col = r[1]
                else:
                    kk = k - 2
                    ri = kk // 3
                    rr_ = kk % 3
                    nrows = max(1, (re - 1 - rt - 2) // 3)
                    dark = 1 if ri >= nrows - 1 else 0
                    if kind == 'thatch':
                        hv = ih(gx, ri, 7) % 5
                        col = r[3] if hv > 1 else (r[4] if hv == 1 else r[2])
                        if rr_ == 2 and hv == 0:
                            col = r[1]
                        if rr_ == 0 and ri == 0:
                            col = r[4]
                    else:
                        seam = (gx + (ri % 2) * 3) % 6 == 0
                        if rr_ == 2:
                            col = r[2 - dark]
                        elif seam and rr_ == 1:
                            col = r[2]
                        elif rr_ == 0:
                            col = r[4 - dark] if ri == 0 else r[3]
                        else:
                            col = r[3 - dark]
                if edge_l or edge_r:
                    col = r[0]
                elif (not lin) and px == ins + 1 and k > 0 and gy < re:
                    col = shade(col, 1)
                elif (not rin) and px == 14 - ins and k > 0 and gy < re:
                    col = shade(col, -1)
                cv.put(gx, gy, col)
        if kind == 'thatch':
            for px in range(1, 15):
                if ih(X + px, 9) % 2:
                    cv.put(X + px, re + 1, r[1])
        if R.snow:
            for px in range(TS):
                gx = X + px
                depth = 4 + (ih(gx // 2, 3) % 3) + (2 if ih(gx // 3, 4) % 3 == 0 else 0)
                for gy in range(rt + 1, min(re - 1, rt + depth)):
                    k = gy - rt
                    ins = max(0, hip - k)
                    if (not lin and px <= ins) or (not rin and px >= 15 - ins):
                        continue
                    col = SN[4] if k < 3 else SN[3]
                    if gy == rt + depth - 1:
                        col = SN[2]
                    if not rin and px == 14 - ins:
                        col = SN[2]
                    cv.put(gx, gy, col)
    # ---- 墙
    for x in xs:
        yt, yb = cols[x]
        X, Y = x * TS, yb * TS
        lin = (x - 1) in cols and cols[x - 1][1] == yb
        rin = (x + 1) in cols and cols[x + 1][1] == yb
        wx0 = X + (0 if lin else 1)
        wx1 = X + 15 - (0 if rin else 1)
        for gx in range(wx0, wx1 + 1):
            for gy in range(Y + wall_top, Y + 15):
                col = plaster[3]
                if gy == Y + wall_top:
                    col = plaster[1]
                elif gy == Y + wall_top + 1:
                    col = plaster[2]
                elif gy == Y + 14:
                    col = plaster[2]
                if gx == wx0 and not lin:
                    col = WO[0]
                elif gx == wx1 and not rin:
                    col = WO[0]
                elif gx == wx0 + 1 and not lin:
                    col = WO[2]
                elif gx == wx1 - 1 and not rin:
                    col = WO[1]
                cv.put(gx, gy, col)
            cv.put(gx, Y + 15, ST[1] if (gx != wx0 or lin) and (gx != wx1 or rin) else ST[0])
        # 房屋右侧投影
        if not rin:
            for gy in range(Y + wall_top, Y + 16):
                cv.darken(wx1 + 1, gy, 1)
        if R.snow:
            for gx in range(wx0 + 1, wx1):
                if ih(gx, 17) % 4 == 0:
                    cv.put(gx, Y + wall_top, SN[4])
                    if ih(gx, 18) % 2:
                        cv.put(gx, Y + wall_top + 1, SN[3])
        ch = m.g[yb][x]
        if ch == 'V':
            draw_door_house(R, X, Y, wall_top)
        else:
            draw_window(R, X, Y, wall_top)
    # 烟囱
    if len(xs) >= 2 and ih(xmin, cols[xmin][0], 610) % 2 == 0:
        x = xs[1] if len(xs) > 2 else xs[ih(xmin, 611) % 2]
        yt = cols[x][0]
        X = x * TS + (3 if x == xs[-1] else 9)
        top = yt * TS - 2
        for gy in range(top, top + 6):
            for gx in range(X, X + 4):
                col = RO[3]
                if gx == X or gx == X + 3:
                    col = RO[0]
                elif gy == top:
                    col = RO[0]
                elif gy == top + 1:
                    col = INK2 if gx in (X + 1, X + 2) else RO[0]
                elif gx == X + 2:
                    col = RO[2]
                cv.put(gx, gy, col)
        if R.snow:
            cv.put(X + 1, top, SN[4]); cv.put(X + 2, top, SN[3])
    # 焚毁（_alt）
    if R.alt:
        for (cx, cy) in comp:
            if m.g[cy][cx] == 'V':
                burn_cell(R, cx, cy, (cx, cy - 1) in cells, wall_top)


def draw_door_house(R, X, Y, wt):
    cv = R.cv
    x0, x1 = X + 5, X + 10
    y0 = Y + wt + 1
    for gy in range(y0, Y + 15):
        for gx in range(x0, x1 + 1):
            k = gy - y0
            if k == 0 and gx in (x0, x1, x0 + 1, x1 - 1):
                if gx in (x0 + 1, x1 - 1):
                    cv.put(gx, gy, WO[0])
                continue
            if k == 1 and gx in (x0, x1):
                cv.put(gx, gy, WO[0])
                continue
            if gx == x0 or gx == x1 or k == 0:
                col = WO[0]
            elif k == 1:
                col = WO[1]
            else:
                col = WO[3] if (gx - x0) % 2 else WO[2]
                if gx == x0 + 1:
                    col = WO[4]
                if gx == x1 - 1:
                    col = WO[1]
            cv.put(gx, gy, col)
    cv.put(x1 - 2, Y + 11, GO[4])
    cv.put(x1 - 2, Y + 12, GO[2])
    # 门阶
    for gx in range(x0 - 1, x1 + 2):
        cv.put(gx, Y + 15, ST[4] if gx < x1 + 1 else ST[2])


def draw_window(R, X, Y, wt):
    cv = R.cv
    x0, x1 = X + 5, X + 10
    y0 = Y + wt + 2
    y1 = y0 + 4
    for gy in range(y0, y1 + 1):
        for gx in range(x0, x1 + 1):
            if gx in (x0, x1) or gy in (y0, y1):
                col = WO[1]
            elif gx == (x0 + x1) // 2 + 1 or gy == y0 + 2:
                col = WO[2]
            else:
                col = INK2
                if gx == x0 + 1 and gy == y0 + 1:
                    col = WA[4]
            cv.put(gx, gy, col)
    for gx in range(x0 - 1, x1 + 2):
        cv.put(gx, y1 + 1, WO[3] if gx < x1 + 1 else WO[1])
    # 花箱
    if ih(X, Y, 21) % 2 and not R.snow and y1 + 2 <= Y + 14:
        for gx in range(x0, x1 + 1):
            cv.put(gx, y1 + 2, WO[2] if gx not in (x0, x1) else WO[0])
            if gx not in (x0, x1):
                cv.put(gx, y1 + 1, (CA[4], G[3], GO[4], G[2])[(gx + Y) % 4])


def char_color(col, k):
    """烧焦：按亮度映射到焦黑色阶；k 为强度 0..1。"""
    lum = (col[0] * 0.3 + col[1] * 0.55 + col[2] * 0.15) / 255.0
    if k > 0.72:
        ramp = [INK, INK2, CB[3], ST[1]]
    elif k > 0.45:
        ramp = [INK2, CB[3], ST[1], ST[2]]
    elif k > 0.25:
        return shade(col, -2)
    elif k > 0.08:
        return shade(col, -1)
    else:
        return col
    i = min(len(ramp) - 1, int(lum * len(ramp) * 1.15))
    return ramp[i]


def burn_cell(R, x, y, roof_above, wt=7):
    """村庄被焚毁：只改动 (x,y) 这一格。上缘两行保持原样以接上方完好的屋顶。"""
    cv = R.cv
    X, Y = x * TS, y * TS
    keep_top = 2 if roof_above else 0
    for py in range(keep_top, TS):
        for px in range(TS):
            gx, gy = X + px, Y + py
            if cv.mat[gy, gx] != M_OBJ and py < 15:
                continue
            ex = min(px, 15 - px)
            k = (0.12, 0.3, 0.5, 0.75)[ex] if ex < 4 else 0.95
            if roof_above and py < 5:
                k = min(k, 0.3 + (py - keep_top) * 0.2)
            if py == 15:
                k = 0.4
            hv = ih(gx, gy, 31) % 100
            if hv < 12:
                k -= 0.3
            col = cv.get(gx, gy)
            cv.put(gx, gy, char_color(col, k), cv.mat[gy, gx])
    # 屋檐烧穿的缺口
    ey = Y + wt - 1
    for px, dh in ((4, 1), (5, 2), (6, 2), (7, 1), (10, 1), (11, 2)):
        for d in range(dh):
            if ey - d >= Y + keep_top + 1:
                cv.put(X + px, ey - d, INK)
    for gx, gy, col in ((X + 5, ey + 1, FI[1]), (X + 6, ey, FI[0]), (X + 11, ey, FI[1]), (X + 4, ey + 1, FI[0])):
        cv.put(gx, gy, col)
    # 塌掉的门洞 + 倒下的焦梁 + 余烬
    y0 = Y + wt
    for gy in range(y0, Y + 15):
        for gx in range(X + 4, X + 12):
            k = gy - y0
            if k == 0 and gx in (X + 4, X + 11):
                continue
            cv.put(gx, gy, INK if k < 4 else INK2)
    for i in range(7):
        cv.put(X + 4 + i, y0 + 1 + i if i < 6 else y0 + 6, WO[0])
        cv.put(X + 5 + i, y0 + 1 + i if i < 5 else y0 + 5, CB[3])
    for i in range(5):
        cv.put(X + 11 - i, y0 + 3 + i, WO[0])
    for gx, gy, col in ((X + 6, Y + 14, FI[2]), (X + 7, Y + 14, FI[3]), (X + 8, Y + 13, FI[1]),
                        (X + 9, Y + 14, FI[2]), (X + 10, Y + 13, FI[0]), (X + 5, Y + 13, FI[0]),
                        (X + 8, Y + 14, FI[4]), (X + 7, Y + 12, FI[0]), (X + 9, y0 + 3, FI[1]),
                        (X + 2, Y + 11, FI[0]), (X + 13, Y + 9, FI[0]), (X + 3, Y + 12, FI[1])):
        cv.put(gx, gy, col)
    # 门前灰烬
    for gx in range(X + 2, X + 14):
        if ih(gx, Y, 33) % 3:
            cv.put(gx, Y + 15, ST[1] if ih(gx, 34) % 2 else ST[2])


# ================================================================== 物件：要塞
def job_fort(R, x, y):
    """要塞：方形石堡，正面垛口 + 顶部平台 + 拱门 + 箭窗 + 旗帜（动画）。"""
    cv = R.cv
    X, Y = x * TS, y * TS
    rk = ST
    snow = R.snow
    top5 = rk[5]
    # 地面阴影
    for gy in range(Y + 4, Y + 16):
        cv.darken(X + 15, gy, 1)
    for gx in range(X + 2, X + 16):
        cv.darken(gx, Y + 15, 1) if gx > X + 13 else None
    # 顶部平台（后墙 + 地面）
    for gx in range(X + 2, X + 14):
        cv.put(gx, Y - 4, rk[0])
        cv.put(gx, Y - 3, SN[4] if snow else rk[4])
        for gy in range(Y - 2, Y + 1):
            cv.put(gx, gy, (SN[3] if snow else rk[2]) if (gx + gy) % 5 else rk[1])
    cv.put(X + 1, Y - 3, rk[0]); cv.put(X + 14, Y - 3, rk[0])
    for gy in range(Y - 2, Y + 2):
        cv.put(X + 1, gy, rk[0]); cv.put(X + 14, gy, rk[0])
    # 正面墙体
    for gy in range(Y + 1, Y + 16):
        for gx in range(X + 1, X + 15):
            k = gy - (Y + 1)
            row = k // 4
            bo = 3 if row % 2 else 0
            col = rk[3]
            if k % 4 == 0:
                col = rk[2]
            elif (gx - X + bo) % 6 == 0:
                col = rk[2]
            elif k % 4 == 1 or (gx - X + bo) % 6 == 1:
                col = rk[4]
            if gx == X + 1 or gx == X + 14:
                col = rk[0]
            elif gx == X + 2:
                col = rk[4] if k % 4 else top5
            elif gx == X + 13:
                col = rk[1]
            if gy == Y + 15:
                col = rk[0] if gx in (X + 1, X + 14) else rk[1]
            cv.put(gx, gy, col)
    # 垛口（正面上沿）
    for gx in range(X + 1, X + 15):
        k = (gx - X - 1) % 4
        if k == 3:
            cv.put(gx, Y + 0, rk[0])
            cv.put(gx, Y + 1, rk[1])
            continue
        cv.put(gx, Y - 2, rk[0])
        cv.put(gx, Y - 1, SN[4] if snow else top5)
        cv.put(gx, Y + 0, rk[4] if k == 0 else (rk[3] if k == 1 else rk[2]))
        cv.put(gx, Y + 1, rk[3] if k != 2 else rk[2])
    for gx in range(X + 1, X + 15):
        cv.put(gx, Y + 2, rk[0] if gx in (X + 1, X + 14) else rk[1])
    # 箭窗
    for gx in (X + 4, X + 11):
        for gy in range(Y + 4, Y + 7):
            cv.put(gx, gy, INK2)
        cv.put(gx, Y + 7, rk[4])
    # 拱门
    for gy in range(Y + 8, Y + 16):
        for gx in range(X + 5, X + 11):
            k = gy - (Y + 8)
            if k == 0 and gx in (X + 5, X + 10):
                continue
            if k == 0:
                col = rk[0]
            elif gx in (X + 5, X + 10):
                col = rk[0]
            elif k == 1:
                col = INK
            else:
                col = INK2 if k < 5 else INK
            cv.put(gx, gy, col)
    for gx in range(X + 6, X + 10, 2):
        cv.put(gx, Y + 9, IR[2]); cv.put(gx, Y + 10, IR[1])
    cv.put(X + 4, Y + 9, rk[4]); cv.put(X + 11, Y + 9, rk[1])
    # 旗帜（动画）：旗杆立在平台右侧
    px = X + 10
    for gy in range(Y - 10, Y - 2):
        cv.put(px, gy, WO[1])
    cv.put(px, Y - 11, GO[4])
    f = R.frame
    for i in range(5):
        off = int(round(math.sin(i * 1.2 - f * 2.1) * 0.7))
        for j in range(3):
            gy = Y - 10 + j + off
            col = (CA[4], CA[3], CA[2])[j]
            if i == 4 and j != 1:
                continue
            cv.put(px + 1 + i, gy, col)
    R.anim_cells.add((x, y))
    R.anim_cells.add((x, y - 1))


# ================================================================== 物件：柱子/王座/祭坛/宝箱/门/城门/废墟/栅栏
def pillar_ramp(R):
    return RO if R.th == 'castle' else ST


def job_pillar(R, x, y):
    cv = R.cv
    X, Y = x * TS, y * TS
    rk = pillar_ramp(R)
    top_i = len(rk) - 1
    # 阴影
    for gy in range(Y + 12, Y + 16):
        for gx in range(X + 12, X + 16):
            cv.darken(gx, gy, 1)
    # 底座
    for gx in range(X + 2, X + 14):
        for gy in range(Y + 11, Y + 15):
            col = rk[3]
            if gy == Y + 11:
                col = rk[top_i]
            elif gy == Y + 14:
                col = rk[1]
            if gx == X + 2 or gx == X + 13:
                col = rk[0]
            cv.put(gx, gy, col)
    for gx in range(X + 2, X + 14):
        cv.put(gx, Y + 15, rk[0] if gx in (X + 2, X + 13) else rk[1])
    # 柱身
    shaft = [0, top_i, top_i - 1, 3, 3, 3, 2, 2, 1, 0]
    for gy in range(Y + 1, Y + 11):
        for i, lv in enumerate(shaft):
            gx = X + 3 + i
            col = rk[lv]
            if i in (3, 6) and (gy % 2 == 0):
                col = shade(col, -1)
            cv.put(gx, gy, col)
    # 柱头（上探 3px）
    for gx in range(X + 2, X + 14):
        for gy in range(Y - 3, Y + 1):
            col = rk[3]
            if gy == Y - 3:
                col = rk[0]
            elif gy == Y - 2:
                col = rk[top_i]
            elif gy == Y:
                col = rk[1]
            if gx == X + 2 or gx == X + 13:
                col = rk[0]
            cv.put(gx, gy, col)


def job_throne(R, x, y):
    cv = R.cv
    X, Y = x * TS, y * TS
    # 台阶
    for gx in range(X, X + 16):
        for gy in range(Y + 12, Y + 16):
            col = RO[4]
            if gy == Y + 12:
                col = RO[5]
            elif gy == Y + 15:
                col = RO[2]
            elif gy == Y + 14:
                col = RO[3]
            if gx == X or gx == X + 15:
                col = RO[1]
            cv.put(gx, gy, col)
    # 靠背
    for gy in range(Y - 6, Y + 8):
        for gx in range(X + 3, X + 13):
            k = gy - (Y - 6)
            if k == 0 and gx not in (X + 7, X + 8):
                continue
            if k == 1 and gx not in (X + 6, X + 7, X + 8, X + 9):
                continue
            if k == 2 and gx in (X + 3, X + 12):
                continue
            edge = gx in (X + 3, X + 12) or k <= 1 or (k == 2 and gx in (X + 4, X + 11))
            inner = X + 5 <= gx <= X + 10 and k >= 4
            if edge:
                col = GO[1]
            elif inner:
                col = CA[3] if gx < X + 9 else CA[2]
                if gx == X + 5:
                    col = CA[4]
                if k == 4:
                    col = CA[1]
            else:
                col = GO[4] if gx in (X + 4, X + 5) else (GO[3] if gx < X + 10 else GO[2])
            cv.put(gx, gy, col)
    # 顶饰（白鹿角）
    cv.put(X + 7, Y - 7, GO[4]); cv.put(X + 8, Y - 7, GO[3])
    cv.put(X + 7, Y - 3, CW[4]); cv.put(X + 8, Y - 3, CW[3])
    cv.put(X + 6, Y - 4, CW[3]); cv.put(X + 9, Y - 4, CW[3])
    # 坐垫 + 扶手 + 座身
    for gy in range(Y + 6, Y + 13):
        for gx in range(X + 1, X + 15):
            k = gy - (Y + 6)
            arm = gx <= X + 3 or gx >= X + 12
            if arm:
                if k < 1:
                    continue
                col = GO[3] if gx in (X + 2, X + 12) else GO[2]
                if k == 1:
                    col = GO[4]
                if gx in (X + 1, X + 14) or k == 6:
                    col = GO[1]
            else:
                if k <= 1:
                    col = CA[4] if k == 0 else CA[3]
                    if gx >= X + 10:
                        col = CA[2]
                else:
                    col = GO[3] if (gx + k) % 4 else GO[4]
                    if gx >= X + 10:
                        col = GO[2]
                    if k == 6:
                        col = GO[1]
            cv.put(gx, gy, col)


def job_altar(R, x, y):
    cv = R.cv
    X, Y = x * TS, y * TS
    for gy in range(Y + 13, Y + 16):
        for gx in range(X + 4, X + 16):
            cv.darken(gx, gy, 1)
    # 石台
    for gy in range(Y + 6, Y + 15):
        for gx in range(X + 1, X + 15):
            col = ST[3]
            if gy <= Y + 7:
                col = ST[5] if gy == Y + 6 else ST[4]
            if gy == Y + 14:
                col = ST[1]
            if gx == X + 1 or gx == X + 14:
                col = ST[0]
            if gy == Y + 6 and gx in (X + 1, X + 14):
                continue
            cv.put(gx, gy, col)
    # 白布
    for gy in range(Y + 6, Y + 13):
        for gx in range(X + 4, X + 12):
            col = CW[3] if gx < X + 10 else CW[2]
            if gy == Y + 6:
                col = CW[4]
            if gy == Y + 12:
                col = GO[3] if gx % 2 else GO[2]
            cv.put(gx, gy, col)
    # 金色白鹿纹
    for gx, gy, col in ((X + 7, Y + 9, GO[3]), (X + 8, Y + 9, GO[3]), (X + 6, Y + 8, GO[3]), (X + 9, Y + 8, GO[3]),
                        (X + 7, Y + 10, GO[2]), (X + 8, Y + 10, GO[2]), (X + 5, Y + 7, GO[2]), (X + 10, Y + 7, GO[2])):
        cv.put(gx, gy, col)
    # 烛台 + 烛火（动画，保持在本格内）
    f = R.frame
    for cxp in (X + 3, X + 12):
        for gy in range(Y + 2, Y + 6):
            cv.put(cxp, gy, CW[4] if gy > Y + 2 else CW[3])
            cv.put(cxp + 1, gy, CW[2])
        cv.put(cxp - 1, Y + 6, GO[2]); cv.put(cxp, Y + 6, GO[3]); cv.put(cxp + 1, Y + 6, GO[3]); cv.put(cxp + 2, Y + 6, GO[1])
        ph = (f + (1 if cxp > X + 8 else 0)) % 3
        fl = [((0, 1, FI[3]), (0, 0, FI[2])), ((0, 1, FI[3]), (1, 0, FI[2]), (0, 0, FI[1])),
              ((0, 1, FI[2]), (0, 0, FI[3]), (0, -1, FI[1]) if False else (1, 1, FI[1]))][ph]
        for dx, dy, col in fl:
            cv.put(cxp + dx, Y + dy, col)
    R.anim_cells.add((x, y))


def job_chest(R, x, y):
    cv = R.cv
    X, Y = x * TS, y * TS
    for gx in range(X + 3, X + 15):
        cv.darken(gx, Y + 15, 1)
    for gy in range(Y + 7, Y + 15):
        cv.darken(X + 14, gy, 1)
    if not R.alt:
        rows = [
            '..oooooooooo..',
            '.olllllllllllo.'[:14],
            'obbbbbbbbbbbbo',
            'ommmmmGGmmmmmo',
            'ogggggyyggggdo',
            'oddddgGGgddddo',
            'ommmmmyymmmmko',
            'ommmmmmmmmmmko',
            'oddddddddddddo',
            'ogggggggggggdo',
            '.oooooooooooo.',
        ]
        leg = {'o': WO[0], 'l': WO[4], 'b': WO[3], 'm': WO[2], 'd': WO[1], 'g': GO[3], 'G': GO[4],
               'y': GO[2], 'k': WO[1]}
        blit(cv, sprite(rows, leg), X + 1, Y + 4)
    else:
        rows = [
            '..oooooooooo..',
            '.oddddddddddo.',
            '.ommmmmmmmmmo.',
            '.oggggyyggggo.',
            'oooooooooooooo',
            'oIIIIIIIIIIIIo',
            'oIkkkkkkkkkkIo',
            'omkkkkkkkkkkmo',
            'ommmmmyymmmmko',
            'oddddddddddddo',
            'ogggggggggggdo',
            '.oooooooooooo.',
        ]
        leg = {'o': WO[0], 'l': WO[4], 'b': WO[3], 'm': WO[2], 'd': WO[1], 'g': GO[3], 'G': GO[4],
               'y': GO[2], 'k': INK2, 'I': WO[3]}
        blit(cv, sprite(rows, leg), X + 1, Y + 3)


def door_floor_color(R, x, y):
    under = R.under[y][x]
    if under == 'ground':
        return G[3] if not R.snow else SN[2]
    if under == 'carpet':
        return CA[3]
    if under == 'prison':
        return ST[2]
    return ST[3] if R.th != 'castle' else RO[4]


def hrun(m, x, y, ch):
    """(x,y) 所在同一行、连续同字符的区间 [x0, x1]。"""
    x0 = x
    while x0 - 1 >= 0 and m.g[y][x0 - 1] == ch:
        x0 -= 1
    x1 = x
    while x1 + 1 < m.w and m.g[y][x1 + 1] == ch:
        x1 += 1
    return x0, x1


def job_door(R, x, y):
    """门：石门框 + 过梁；关着是带铁箍的木门，_alt 中门扇贴到门柱、露出门洞里的地面。
    同一行相邻的多个 D 画成一扇宽门：每格各自是一扇门扇，开/关只改动本格 16×16。"""
    m, cv = R.m, R.cv
    X, Y = x * TS, y * TS
    st = wall_style(R)
    rk = st['r']
    hi = rk[5] if len(rk) > 5 else rk[4]
    x0, x1 = hrun(m, x, y, 'D')
    le, re_ = x == x0, x == x1
    single = le and re_
    # 过梁
    pa = 1 if le else 0
    pb = 14 if re_ else 15
    for px in range(pa, pb + 1):
        gx = X + px
        edge = (le and px == 1) or (re_ and px == 14)
        cv.put(gx, Y + 3, rk[0], M_WALL)
        cv.put(gx, Y + 4, rk[0] if edge else (hi if not (re_ and px == 13) else rk[2]), M_WALL)
        cv.put(gx, Y + 5, rk[0] if edge else (rk[3] if (gx % 4) else rk[2]), M_WALL)
    # 门柱
    for gy in range(Y + 5, Y + 16):
        if le:
            cv.put(X + 1, gy, rk[0], M_WALL)
            cv.put(X + 2, gy, hi if (gy - Y) % 4 else rk[3], M_WALL)
        if re_:
            cv.put(X + 13, gy, rk[2] if (gy - Y) % 4 else rk[1], M_WALL)
            cv.put(X + 14, gy, rk[0], M_WALL)
    la = 3 if le else 0          # 本格门扇范围
    lb = 12 if re_ else 15
    if not R.alt:
        for gy in range(Y + 6, Y + 16):
            k = gy - (Y + 6)
            for px in range(la, lb + 1):
                gx = X + px
                i = px - la
                if k == 0 or (le and px == la) or (re_ and px == lb):
                    col = WO[0]
                elif single and px in (7, 8):
                    col = WO[0] if px == 8 else WO[1]
                elif (not re_) and px == 15:
                    col = WO[0]                       # 与右邻门扇的对缝
                elif (not le) and px == 0:
                    col = WO[1]
                else:
                    col = WO[3] if (gx % 2) else WO[2]
                    if i == 1:
                        col = WO[4]
                    if k == 1:
                        col = WO[1]
                if k in (2, 7) and col not in (WO[0],):
                    col = IR[2] if (gx % 3) else IR[4]
                cv.put(gx, gy, col, M_WALL)
        # 门环：单格在中缝，多格在每扇靠对缝一侧
        if single:
            ring = [(7, 10, GO[4]), (8, 10, GO[3]), (7, 11, GO[2]), (8, 11, GO[1]), (6, 11, IR[1]), (9, 11, IR[1])]
        else:
            rx = 13 if not re_ else 2
            if le and not re_:
                rx = 13
            ring = [(rx, 10, GO[4]), (rx, 11, GO[2]), (rx - 1 if rx > 8 else rx + 1, 11, IR[1])]
        for px, py, col in ring:
            cv.put(X + px, Y + py, col, M_WALL)
    else:
        base = door_floor_color(R, x, y)
        for gy in range(Y + 6, Y + 16):
            k = gy - (Y + 6)
            for px in range(la, lb + 1):
                if k <= 1:
                    col = INK
                elif k <= 3:
                    col = shade(base, -2)
                elif k <= 5:
                    col = shade(base, -1)
                else:
                    col = base
                cv.put(X + px, gy, col, M_GROUND)
        # 推开贴在门柱边的门扇（侧看成窄条）；多格门的中间格没有门柱，门扇收到画面外
        for gy in range(Y + 6, Y + 16):
            top = gy == Y + 6
            if le:
                cv.put(X + 3, gy, WO[0] if top else WO[3], M_WALL)
                cv.put(X + 4, gy, WO[0] if top else WO[1], M_WALL)
            if re_:
                cv.put(X + 11, gy, WO[0] if top else WO[2], M_WALL)
                cv.put(X + 12, gy, WO[0] if top else WO[1], M_WALL)
        for px in ((3, 4) if le else ()) + ((11, 12) if re_ else ()):
            cv.put(X + px, Y + 8, IR[2], M_WALL)
            cv.put(X + px, Y + 13, IR[2], M_WALL)


def job_gate(R, x, y):
    """城门：同一行相邻的多个 G 画成一座宽拱门（在该行最左一格统一绘制）；
    下方仍是 G 的格（厚墙中段）画成穿墙通道。"""
    m, cv = R.m, R.cv
    st = wall_style(R)
    rk = st['r']
    hi = rk[5] if len(rk) > 5 else rk[4]
    x0, x1 = hrun(m, x, y, 'G')
    passage = m.at(x, y + 1) == 'G' and y + 1 < m.h

    def ends(cx):
        yy = y
        while m.at(cx, yy - 1) == 'G' and yy > 0:
            yy -= 1
        a = m.at(cx, yy - 1)
        yy = y
        while m.at(cx, yy + 1) == 'G' and yy < m.h - 1:
            yy += 1
        return a, m.at(cx, yy + 1)
    under = R.under[y][x]
    if any(e in '"=' for cx in range(x0, x1 + 1) for e in ends(cx)):
        base, base2 = (RO[4], RO[3]) if R.th == 'castle' else ((ST[4], ST[3]) if R.th == 'indoor' else (
            (SN[2], SN[1]) if R.snow else (EA[4], EA[3])))
    elif under == 'ground':
        base, base2 = (SN[3], SN[2]) if R.snow else (G[4], G[3])
    else:
        base, base2 = (RO[4], RO[3]) if R.th == 'castle' else (ST[3], ST[2])
    Y = y * TS
    if passage:
        # 厚墙中的穿墙通道（俯视）：两端是墙顶，中间是延续的路面
        X = x * TS
        top_c = rk[st['top']]
        for gy in range(Y, Y + 16):
            for px in range(16):
                gx = X + px
                wall_l = (x == x0) and px <= 2
                wall_r = (x == x1) and px >= 13
                if wall_l or wall_r:
                    col = top_c if (gy % 8) else rk[st['top'] - 1]
                    if px in (2, 13):
                        col = rk[0]
                    elif px in (1, 14):
                        col = rk[3]
                    cv.put(gx, gy, col, M_WALL)
                else:
                    col = base if (gy + (gx // 3)) % 4 else base2
                    if x == x0 and px == 3:
                        col = shade(base, -2)
                    elif x == x1 and px == 12:
                        col = shade(base, -1)
                    cv.put(gx, gy, col, M_GROUND)
        return
    if x != x0:
        return                                     # 宽拱门在最左格统一画
    XA = x0 * TS
    XB = x1 * TS + 15
    Wd = XB - XA + 1
    # 门楼外框
    for gy in range(Y + 3, Y + 16):
        k = gy - (Y + 3)
        for gx in range(XA, XB + 1):
            col = rk[3]
            if (gx - XA) % 4 == 0 and k > 2:
                col = rk[2]
            if k == 0:
                col = rk[0]
            elif k == 1:
                col = hi
            elif k == 2:
                col = rk[4]
            if gx == XA and k > 0:
                col = rk[4]
            if gx == XB and k > 0:
                col = rk[1]
            cv.put(gx, gy, col, M_WALL)
    # 拱形门洞：两端低、中间高
    oa, ob = XA + 3, XB - 3
    ow = ob - oa + 1
    tops = {}
    for gx in range(oa, ob + 1):
        u = (gx - oa + 0.5) / ow
        lift = math.sin(math.pi * u)
        tops[gx] = Y + 8 - int(round(lift * (2 if ow <= 12 else 3)))
    for gx in range(oa, ob + 1):
        for gy in range(tops[gx], Y + 16):
            k = gy - tops[gx]
            if k <= 2:
                col = INK
            elif k <= 4:
                col = shade(base2, -2)
            elif k <= 6:
                col = base2
            else:
                col = base
            cv.put(gx, gy, col, M_GROUND if k > 2 else M_WALL)
        # 拱石
        cv.put(gx, tops[gx] - 1, hi if (gx % 3) else rk[1], M_WALL)
        cv.put(gx, tops[gx] - 2, rk[1], M_WALL)
    # 升起的铁闸齿
    for gx in range(oa + 1, ob, 2):
        t = tops[gx]
        cv.put(gx, t, IR[2]); cv.put(gx, t + 1, IR[3]); cv.put(gx, t + 2, IR[1])
    # 门侧立柱
    for gy in range(Y + 6, Y + 16):
        cv.put(oa - 1, gy, rk[0], M_WALL)
        cv.put(ob + 1, gy, rk[0], M_WALL)
        cv.put(oa - 2, gy, hi if gy % 3 else rk[2], M_WALL)
        cv.put(ob + 2, gy, rk[2] if gy % 3 else rk[1], M_WALL)
    # 宽门中间的分隔柱（每两格之间一根细柱，托住拱顶）
    if x1 > x0 and Wd >= 40:
        for cx in range(x0 + 1, x1 + 1):
            gx = cx * TS
            for gy in range(tops.get(gx, Y + 8), Y + 16):
                cv.put(gx - 1, gy, rk[4], M_WALL)
                cv.put(gx, gy, rk[2], M_WALL)


def job_ruins(R, x, y):
    """废墟：一段横跨整格、中间塌出大缺口的断墙 + 前方散落石块（可通行地形）。"""
    cv = R.cv
    X, Y = x * TS, y * TS
    rk = ST if (R.snow or R.th == 'indoor') else RO
    hi = rk[5] if len(rk) > 5 else rk[4]
    snow = R.snow
    flip = ih(x, y, R.seed, 700) % 2
    prof = [3, 2, 2, 2, 3, 3, 6, 6, 6, 9, 9, 10, 7, 7]
    if flip:
        prof = prof[::-1]
    x0, x1 = X + 1, X + 14
    ybot = Y + 12
    tops = {x0 + i: Y + p for i, p in enumerate(prof)}
    for gx in range(x0, x1 + 1):
        t = tops[gx]
        for gy in range(t, ybot + 1):
            kk = gy - Y
            bo = 3 if (kk // 3) % 2 else 0
            col = rk[3]
            if gy == t:
                col = SN[4] if snow else hi
            elif gy == t + 1:
                col = SN[3] if snow else rk[4]
            elif kk % 3 == 0:
                col = rk[2]
            elif (gx + bo) % 5 == 0:
                col = rk[2]
            elif (gx + bo) % 5 == 1:
                col = rk[4]
            if gx == x0 or gx == x1:
                col = rk[0]
            if gy == ybot:
                col = rk[0]
            cv.put(gx, gy, col)
        cv.put(gx, t - 1, rk[0])
        # 相邻列落差处补竖描边
        for nx in (gx - 1, gx + 1):
            if nx in tops and tops[nx] > t + 1:
                for gy in range(t, tops[nx]):
                    cv.put(gx, gy, rk[0] if gy > t else cv.get(gx, gy))
    # 墙右侧与墙脚阴影
    for gy in range(Y + 4, ybot + 2):
        cv.darken(x1 + 1, gy, 1)
    # 缺口前的碎石堆
    mid = x0 + (8 if not flip else 2)
    for dx, dy, lv in ((0, 0, 4), (1, 0, 3), (2, 0, 3), (3, 0, 2), (1, -1, 4), (2, -1, 2),
                       (-1, 1, 3), (0, 1, 2), (1, 1, 2), (2, 1, 1), (3, 1, 1), (4, 1, 2)):
        cv.put(mid + dx, ybot + 1 + dy, rk[lv] if not (snow and dy < 0) else SN[4])
    for i in range(3):
        hv = ih(x, y, 710 + i)
        gx = X + 1 + hv % 13
        gy = Y + 14 + (hv >> 8) % 2
        cv.put(gx, gy, rk[4])
        cv.put(gx + 1, gy, rk[2])
    if not snow and R.th != 'indoor':
        for gx, gy, col in ((x0 + 1, ybot - 1, G[2]), (x0 + 2, ybot - 1, G[3]), (x0 + 1, ybot - 2, G[3]),
                            (x1 - 2, ybot - 1, G[3]), (x1 - 1, ybot - 1, G[2])):
            cv.put(gx, gy, col)


def job_fence(R, x, y):
    m, cv = R.m, R.cv
    X, Y = x * TS, y * TS
    L = m.at(x - 1, y) == 'f' and x > 0
    Rr = m.at(x + 1, y) == 'f' and x < m.w - 1
    U = m.at(x, y - 1) == 'f' and y > 0
    D = m.at(x, y + 1) == 'f' and y < m.h - 1
    horiz = L or Rr or not (U or D)
    snow = R.snow

    def post(px, top, bot=13):
        for gy in range(Y + top, Y + bot):
            cv.put(X + px - 1, gy, WO[0])
            cv.put(X + px, gy, WO[3] if gy > Y + top else WO[4])
            cv.put(X + px + 1, gy, WO[1] if gy > Y + top else WO[2])
            cv.put(X + px + 2, gy, WO[0])
        cv.put(X + px, Y + top - 1, WO[0]); cv.put(X + px + 1, Y + top - 1, WO[0])
        cv.put(X + px, Y + bot, WO[0]); cv.put(X + px + 1, Y + bot, WO[0])
        if snow:
            cv.put(X + px, Y + top - 1, SN[4]); cv.put(X + px + 1, Y + top - 1, SN[3])
        cv.darken(X + px + 2, Y + bot, 1)
        cv.darken(X + px + 3, Y + bot, 1)

    if horiz:
        x0 = 0 if L else 2
        x1 = 15 if Rr else 13
        for gx in range(X + x0, X + x1 + 1):
            for ry in (7, 10):
                cv.put(gx, Y + ry - 1, WO[0])
                cv.put(gx, Y + ry, SN[4] if (snow and ry == 7) else WO[4])
                cv.put(gx, Y + ry + 1, WO[2])
                cv.put(gx, Y + ry + 2, WO[0] if ry == 10 else WO[1])
            cv.darken(gx, Y + 13, 1)
            cv.darken(gx, Y + 14, 1)
        post(3, 5)
        post(11, 5)
    if U or D:
        # 南北向栅栏：一根连续横木（俯视成竖线）+ 两根短桩
        y0 = 0 if U else 5
        y1 = 15 if D else 12
        for gy in range(Y + y0, Y + y1 + 1):
            cv.put(X + 6, gy, WO[0]); cv.put(X + 7, gy, WO[4] if not snow else SN[4]); cv.put(X + 8, gy, WO[2]); cv.put(X + 9, gy, WO[0])
            cv.darken(X + 10, gy, 1)
        if not horiz:
            post(7, 3 if U else 5, 8)
        post(7, 10, 15 if D else 13)


# ================================================================== 物件调度
def paint_objects(R):
    m = R.m
    jobs = []
    for x, y in m.cells('T'):
        jobs.append((y, x, 0, job_forest))
    for x, y in m.cells('h'):
        jobs.append((y, x, 0, job_hill))
    for x, y in m.cells(MOUNT):
        jobs.append((y, x, 0, job_mountain))
    for x, y in m.cells('F'):
        jobs.append((y, x, 0, job_fort))
    for x, y in m.cells('|'):
        jobs.append((y, x, 0, job_pillar))
    for x, y in m.cells('K'):
        jobs.append((y, x, 0, job_throne))
    for x, y in m.cells('a'):
        jobs.append((y, x, 0, job_altar))
    for x, y in m.cells('C'):
        jobs.append((y, x, 0, job_chest))
    for x, y in m.cells('D'):
        jobs.append((y, x, 0, job_door))
    for x, y in m.cells('G'):
        jobs.append((y, x, 0, job_gate))
    for x, y in m.cells('r'):
        jobs.append((y, x, 0, job_ruins))
    for x, y in m.cells('f'):
        jobs.append((y, x, 0, job_fence))
    for comp in components(m, HOUSE):
        yb = max(p[1] for p in comp)
        xb = min(p[0] for p in comp)
        jobs.append((yb, xb, 1, lambda R, x, y, comp=comp: draw_house(R, comp)))
    jobs.sort(key=lambda j: (j[0], j[1], j[2]))
    for y, x, _, fn in jobs:
        fn(R, x, y)


# ================================================================== 总流程
def render(m, frame=0, alt=False):
    R = Ctx(m, frame, alt)
    paint_ground(R)
    paint_roads(R)
    paint_water(R)
    paint_cliffs(R)
    paint_mountain_bg(R)
    paint_walls(R)
    paint_stairs(R)
    paint_bridges(R)
    paint_objects(R)
    img = Image.fromarray(R.cv.c, 'RGBA')
    return img, R


def verify(m, frames, alt, anim_cells):
    """自检：_alt 与第 0 帧的差异只在 D/C/V 格内；可变格内不应有动画像素。"""
    a0 = np.asarray(frames[0]).astype(np.int32)
    ok = True
    diff = np.any(np.asarray(alt).astype(np.int32) != a0, axis=2)
    ys, xs = np.nonzero(diff)
    bad = set()
    for y, x in zip(ys.tolist(), xs.tolist()):
        cx, cy = x // TS, y // TS
        if m.g[cy][cx] not in MUTABLE:
            bad.add((cx, cy))
    if bad:
        ok = False
        print('  [错误] _alt 在非可变格有差异：', sorted(bad)[:10])
    for fi in (1, 2):
        d = np.any(np.asarray(frames[fi]).astype(np.int32) != a0, axis=2)
        ys, xs = np.nonzero(d)
        hit = set()
        for y, x in zip(ys.tolist(), xs.tolist()):
            cx, cy = x // TS, y // TS
            if m.g[cy][cx] in MUTABLE:
                hit.add((cx, cy))
        if hit:
            print('  [提示] 可变格内有动画像素（贴 _alt 时会冻结）：', sorted(hit)[:10])
    for im in list(frames) + [alt]:
        a = np.asarray(im)
        if (a[:, :, 3] != 255).any():
            ok = False
            print('  [错误] 存在非不透明像素')
            break
    return ok


def process(path, preview=True):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    m = Map(data)
    frames = []
    anim = set()
    for fi in range(3):
        img, R = render(m, fi, False)
        frames.append(img)
        anim |= R.anim_cells
    alt, _ = render(m, 0, True)
    os.makedirs(OUT_DIR, exist_ok=True)
    for fi, img in enumerate(frames):
        img.save(os.path.join(OUT_DIR, '%s_%d.png' % (m.id, fi)))
    alt.save(os.path.join(OUT_DIR, '%s_alt.png' % m.id))
    ok = verify(m, frames, alt, anim)
    if preview:
        os.makedirs(PREV_DIR, exist_ok=True)
        sc = 2
        W, H = frames[0].size
        sheet = Image.new('RGBA', (W * sc, H * sc), (0, 0, 0, 255))
        sheet.paste(frames[0].resize((W * sc, H * sc), Image.NEAREST), (0, 0))
        sheet.save(os.path.join(PREV_DIR, '%s.png' % m.id))
        alt.resize((W * sc, H * sc), Image.NEAREST).save(os.path.join(PREV_DIR, '%s_alt.png' % m.id))
    print('%s: %dx%d 格 -> assets/maps/%s_[0-2|alt].png %s' % (m.id, m.w, m.h, m.id, '' if ok else '（自检未通过）'))
    return ok


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description='《灰烬王冠》地图绘制器')
    ap.add_argument('files', nargs='*')
    ap.add_argument('--samples', action='store_true', help='只处理 sample_*.json')
    ap.add_argument('--no-samples', action='store_true', help='跳过 sample_*.json')
    ap.add_argument('--no-preview', action='store_true')
    a = ap.parse_args(argv)
    files = a.files
    if not files:
        files = sorted(glob.glob(os.path.join(MAPS_DIR, '*.json')))
        if a.samples:
            files = [f for f in files if os.path.basename(f).startswith('sample_')]
        if a.no_samples:
            files = [f for f in files if not os.path.basename(f).startswith('sample_')]
    if not files:
        print('没有找到地图文件')
        return 1
    allok = True
    for f in files:
        allok &= process(f, not a.no_preview)
    return 0 if allok else 1


if __name__ == '__main__':
    sys.exit(main())
