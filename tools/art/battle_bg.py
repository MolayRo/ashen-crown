# -*- coding: utf-8 -*-
"""
战斗背景（320x124）与站台（100x20）—— battle_bg.png / .json。
画风：SNES/GBA 战斗背景，远景简洁、对比度低于角色；地平线附近留给站台。
地面线约在 y=108（站台顶面），所以背景下半部分画地面/远处地表。
全部颜色吸附到 palette.py 色阶。
"""
import math
import os
import json
import numpy as np
from PIL import Image
from palette import PAL, INK, INK2
from battle_fx import FX, rng, snap_palette

BW, BH = 320, 124
PW, PH = 100, 20

BG_PAL = [INK, INK2] + [c for k, v in PAL.items() if not k.startswith('eye_') for c in v]


def C(name, i):
    return PAL[name][i]


def bands(f, y0, y1, cols, dither=True):
    """纵向色带（天空渐变），带 2 行棋盘格过渡。"""
    n = len(cols)
    for i, c in enumerate(cols):
        a = y0 + (y1 - y0) * i / n
        b = y0 + (y1 - y0) * (i + 1) / n
        f.put((f.y >= a) & (f.y < b), c)
        if dither and i > 0:
            m = (f.y >= a - 2) & (f.y < a) & (((np.floor(f.x) + np.floor(f.y)) % 2) == 0)
            f.put(m, c)


def ridge(f, base, amp, seed, freq=(0.013, 0.031, 0.07), wts=(1.0, 0.45, 0.2)):
    rs = rng(seed)
    ph = rs.uniform(0, 6.28, len(freq))
    x = np.arange(f.w) + 0.5
    h = np.zeros(f.w)
    for fr, w, p in zip(freq, wts, ph):
        h += np.sin(x * fr * 6.28 + p) * w
    h = h / sum(wts)
    return base - amp * (0.5 + 0.5 * h)


def fill_below(f, top, color, alpha=1.0, bottom=None):
    t = top[None, :]
    m = f.y >= t
    if bottom is not None:
        m &= f.y < bottom
    f.put(m, color, alpha)


def mountains(f, base, amp, seed, cols, snowcap=None, jag=True):
    """山体：cols=(亮面, 基色, 暗面)；按坡度给左侧受光面上亮色。"""
    top = ridge(f, base, amp, seed, freq=(0.010, 0.027, 0.061) if jag else (0.006, 0.015, 0.03))
    if jag:
        rs = rng(seed + 1)
        top = top - np.abs(np.sin(np.arange(f.w) * 0.21 + rs.uniform(0, 6))) * amp * 0.08
    fill_below(f, top, cols[1])
    slope = np.gradient(top)
    # 坡面：朝左上（高度向右减小 → slope>0 表示向右下降）
    lit = slope < -0.15
    shade = slope > 0.25
    for x in range(f.w):
        t0 = top[x]
        if lit[x]:
            f.put((f.x >= x) & (f.x < x + 1) & (f.y >= t0) & (f.y < t0 + amp * 0.5), cols[0])
        elif shade[x]:
            f.put((f.x >= x) & (f.x < x + 1) & (f.y >= t0 + 1) & (f.y < t0 + amp * 0.6), cols[2])
    if snowcap is not None:
        hi = top < (base - amp * 0.55)
        rs = rng(seed + 7)
        jag = np.abs(np.sin(np.arange(f.w) * 0.9 + rs.uniform(0, 6))) * 3.0
        depth = np.clip((base - amp * 0.55) - top, 0, None) * 0.9 + jag
        cap = top + depth
        m = (f.y >= top[None, :]) & (f.y < cap[None, :]) & hi[None, :]
        f.put(m, snowcap)
    return top


def cloud(f, x, y, w, cols, seed=0):
    """蓬松云：cols=(阴影, 基色, 高光)。底部平、上部鼓包。"""
    rs = rng(seed)
    n = max(3, int(w / 8))
    bumps = []
    for i in range(n):
        cx = x + w * (i + 0.5) / n + rs.uniform(-1.5, 1.5)
        r = rs.uniform(4.0, 6.5) * (1.0 - abs(i - (n - 1) / 2) / n * 0.9)
        bumps.append((cx, y - r * 0.35, r))
    base = (f.y <= y + 3.0) & (np.abs(f.x - x - w / 2) <= w / 2)
    body = np.zeros_like(base)
    for cx, cy, r in bumps:
        body |= (f.x - cx) ** 2 + (f.y - cy) ** 2 <= r * r
    body &= f.y <= y + 3.0
    body |= base & (f.y >= y - 1.0)
    f.put(body, cols[1])
    # 高光：每个鼓包的左上
    for cx, cy, r in bumps:
        f.put(((f.x - cx + r * 0.3) ** 2 + (f.y - cy + r * 0.3) ** 2 <= (r * 0.55) ** 2) & body, cols[2])
    # 阴影：底部两行
    f.put(body & (f.y > y + 1.0), cols[0])


def tree_round(f, x, base, h, r, cols, trunk):
    f.put((np.abs(f.x - x) < 1.5) & (f.y > base - h * 0.45) & (f.y < base), trunk)
    cy = base - h * 0.55
    f.disk(x, cy, r, cols[1])
    f.disk(x - r * 0.35, cy - r * 0.35, r * 0.55, cols[2])
    f.put(((f.x - x) ** 2 + (f.y - cy) ** 2 <= r * r) & (f.y > cy + r * 0.45), cols[0])


def pine(f, x, base, h, w, cols, trunk=None, snow=None):
    if trunk is not None:
        f.put((np.abs(f.x - x) < 1.0) & (f.y > base - 3) & (f.y < base), trunk)
    tiers = 3
    for i in range(tiers):
        tb = base - 2 - i * h * 0.27
        tt = tb - h * 0.42
        tw = w * (1.0 - i * 0.24)
        f.poly([(x, tt), (x + tw / 2, tb), (x - tw / 2, tb)], cols[1])
        f.poly([(x, tt), (x - tw / 2, tb), (x - tw * 0.1, tb)], cols[2])
        if snow is not None:
            f.poly([(x, tt), (x + tw * 0.22, tt + h * 0.14), (x - tw * 0.26, tt + h * 0.16)], snow)
            f.put((f.y > tb - 1.2) & (f.y < tb) & (np.abs(f.x - x) < tw / 2 - 0.5), snow)


def grass_ground(f, y0, cols, seed, tufts=True):
    """草地：从地平线到底部的色带 + 草丛纹理。"""
    bands(f, y0, BH, cols, dither=True)
    if tufts:
        rs = rng(seed)
        for i in range(260):
            x = rs.uniform(0, BW)
            y = rs.uniform(y0 + 2, BH)
            s = 1 + (y - y0) / (BH - y0) * 1.5
            f.line((x, y), (x + s * 0.5, y - s * 1.5), cols[min(len(cols) - 1, 1)])
            f.pix(x - 1, y, cols[0])


# ================================================================ 背景
def bg_plains():
    f = FX(BW, BH)
    bands(f, 0, 70, [C('cloth_sky', 2), C('cloth_sky', 3), C('cloth_sky', 3), C('cloth_sky', 4)])
    cloud(f, 30, 20, 44, (C('cloth_white', 2), C('cloth_white', 3), C('cloth_white', 4)), 1)
    cloud(f, 190, 13, 60, (C('cloth_white', 2), C('cloth_white', 3), C('cloth_white', 4)), 2)
    cloud(f, 270, 34, 30, (C('cloth_white', 2), C('cloth_white', 3), C('cloth_white', 4)), 3)
    mountains(f, 72, 30, 11, (C('cloth_sky', 3), C('cloth_sky', 2), C('team_blue', 3)),
              snowcap=C('cloth_white', 3))
    mountains(f, 80, 16, 12, (C('grass', 2), C('forest', 3), C('forest', 2)), jag=False)
    # 远处树丛带
    rs = rng(5)
    for i in range(40):
        x = rs.uniform(0, BW)
        tree_round(f, x, 84 + rs.uniform(0, 2), 9, rs.uniform(3, 4.5), (C('forest', 1), C('forest', 2), C('forest', 3)),
                   C('wood', 1))
    grass_ground(f, 84, [C('grass', 2), C('grass', 3), C('grass', 3), C('grass', 4)], 7)
    # 小花
    rs = rng(9)
    for i in range(40):
        x, y = rs.uniform(0, BW), rs.uniform(92, BH)
        f.pix(x, y, [C('cloth_white', 4), C('gold', 4), C('team_red', 4)][i % 3])
    return f


def bg_forest():
    f = FX(BW, BH)
    bands(f, 0, 60, [C('cloth_sky', 2), C('cloth_sky', 3), C('heal', 2), C('grass', 4)])
    # 远景树林剪影（两层）
    rs = rng(21)
    for i in range(34):
        x = i * 10 + rs.uniform(-3, 3)
        pine(f, x, 70 + rs.uniform(-3, 3), 44 + rs.uniform(-6, 8), 16, (C('forest', 1), C('forest', 2), C('forest', 3)))
    top = ridge(f, 70, 6, 22)
    fill_below(f, top, C('forest', 1))
    rs = rng(23)
    for i in range(20):
        x = i * 17 + rs.uniform(-4, 4)
        pine(f, x, 88 + rs.uniform(-2, 2), 58 + rs.uniform(-6, 6), 22,
             (C('forest', 0), C('forest', 1), C('forest', 2)), trunk=C('wood', 0))
    # 近景粗树干
    for x, w in ((22, 7), (118, 5), (205, 8), (296, 6)):
        f.put((np.abs(f.x - x) < w) & (f.y < 96), C('wood', 1))
        f.put((f.x > x - w) & (f.x < x - w + 2) & (f.y < 96), C('wood', 2))
        f.put((f.x > x + w - 2) & (f.x < x + w) & (f.y < 96), C('wood', 0))
        for yy in (18, 44, 70):
            f.line((x - w + 2, yy), (x - 1, yy + 3), C('wood', 0))
    # 顶部树冠
    rs = rng(24)
    for i in range(30):
        f.disk(rs.uniform(0, BW), rs.uniform(-6, 8), rs.uniform(8, 14), C('forest', 1 + i % 2))
    grass_ground(f, 92, [C('forest', 2), C('forest', 3), C('grass', 2), C('grass', 3)], 25)
    # 林间光斑
    rs = rng(26)
    for i in range(14):
        f.ell(rs.uniform(0, BW), rs.uniform(98, 120), rs.uniform(4, 9), 1.5, C('grass', 4), 1.0)
    return f


def house(f, x, base, w, h, roof, wall, timber, door=True, seed=0):
    rs = rng(seed)
    f.put((f.x >= x) & (f.x < x + w) & (f.y >= base - h) & (f.y < base), wall[1])
    f.put((f.x >= x) & (f.x < x + 2) & (f.y >= base - h) & (f.y < base), wall[2])
    f.put((f.x >= x + w - 2) & (f.x < x + w) & (f.y >= base - h) & (f.y < base), wall[0])
    # 木筋
    for yy in (base - h + 1, base - h * 0.5, base - 1):
        f.put((f.x >= x) & (f.x < x + w) & (f.y >= yy) & (f.y < yy + 1), timber)
    for xx in np.arange(x, x + w, 7):
        f.put((f.x >= xx) & (f.x < xx + 1) & (f.y >= base - h) & (f.y < base), timber)
    # 屋顶
    rh = h * 0.8
    f.poly([(x - 3, base - h), (x + w / 2, base - h - rh), (x + w + 3, base - h)], roof[2])
    f.poly([(x - 3, base - h), (x + w / 2, base - h - rh), (x + w / 2 - 2, base - h)], roof[3])
    f.put((f.y >= base - h - 1) & (f.y < base - h + 0.5) & (f.x > x - 3) & (f.x < x + w + 3), roof[1])
    # 窗与门
    f.put((f.x >= x + 4) & (f.x < x + 8) & (f.y >= base - h + 4) & (f.y < base - h + 8), C('fire', 3))
    f.put((f.x >= x + 4) & (f.x < x + 8) & (f.y >= base - h + 6) & (f.y < base - h + 6.9), timber)
    if door:
        dx = x + w - 11
        f.put((f.x >= dx) & (f.x < dx + 6) & (f.y >= base - 10) & (f.y < base), C('wood', 1))
        f.put((f.x >= dx) & (f.x < dx + 1) & (f.y >= base - 10) & (f.y < base), C('wood', 3))


def bg_village():
    f = FX(BW, BH)
    bands(f, 0, 72, [C('cloth_sky', 2), C('cloth_sky', 3), C('cloth_sky', 4)])
    cloud(f, 60, 18, 50, (C('cloth_white', 2), C('cloth_white', 3), C('cloth_white', 4)), 5)
    cloud(f, 230, 26, 40, (C('cloth_white', 2), C('cloth_white', 3), C('cloth_white', 4)), 6)
    mountains(f, 74, 18, 31, (C('grass', 3), C('forest', 3), C('forest', 2)), jag=False)
    rs = rng(32)
    for i in range(30):
        tree_round(f, rs.uniform(0, BW), 80, 12, rs.uniform(4, 6), (C('forest', 1), C('forest', 2), C('forest', 3)),
                   C('wood', 1))
    wall = (C('earth', 2), C('earth', 3), C('earth', 4))
    roof = PAL['roof_red']
    for i, (x, w, h) in enumerate(((12, 34, 16), (70, 26, 13), (150, 38, 18), (232, 30, 14), (282, 34, 16))):
        house(f, x, 90, w, h, roof, wall, C('wood', 1), seed=i)
    # 篱笆
    for x in range(0, BW, 6):
        f.put((f.x >= x) & (f.x < x + 1) & (f.y >= 86) & (f.y < 92), C('wood', 2))
    f.put((f.y >= 87) & (f.y < 88), C('wood', 3))
    f.put((f.y >= 90) & (f.y < 91), C('wood', 1))
    # 土路地面
    bands(f, 92, BH, [C('earth', 2), C('earth', 3), C('earth', 3), C('grass', 3)])
    rs = rng(33)
    for i in range(200):
        x, y = rs.uniform(0, BW), rs.uniform(94, BH)
        f.pix(x, y, C('earth', 1 + (i % 3 == 0) * 3))
    return f


def bg_bridge():
    f = FX(BW, BH)
    bands(f, 0, 64, [C('cloth_sky', 2), C('cloth_sky', 3), C('cloth_sky', 4)])
    cloud(f, 110, 18, 56, (C('cloth_white', 2), C('cloth_white', 3), C('cloth_white', 4)), 7)
    mountains(f, 62, 22, 41, (C('cloth_sky', 3), C('cloth_sky', 2), C('team_blue', 3)))
    # 对岸：树林 + 断掉的石桥
    top = ridge(f, 72, 6, 42)
    fill_below(f, top, C('forest', 2))
    rs = rng(43)
    for i in range(36):
        tree_round(f, rs.uniform(0, BW), 74 + rs.uniform(-1, 2), 11, rs.uniform(3.5, 5.5),
                   (C('forest', 1), C('forest', 2), C('forest', 3)), C('wood', 1))
    f.put(f.y >= 76, C('earth', 2))
    f.put((f.y >= 76) & (f.y < 77), C('earth', 3))
    # 河流
    bands(f, 78, BH, [C('water', 3), C('water', 2), C('water', 2), C('water', 1)])
    rs = rng(44)
    for i in range(90):
        x, y = rs.uniform(0, BW), rs.uniform(80, BH)
        l = rs.uniform(3, 10) * (0.6 + (y - 78) / 46)
        f.line((x, y), (x + l, y), C('water', 4) if i % 3 else C('water', 5))
    # 远处的断石桥（右侧）
    for i, x in enumerate((238, 262, 286)):
        f.put((f.x >= x) & (f.x < x + 8) & (f.y >= 70) & (f.y < 84), C('stone', 3))
        f.put((f.x >= x) & (f.x < x + 2) & (f.y >= 70) & (f.y < 84), C('stone', 4))
        f.put((f.x >= x + 6) & (f.x < x + 8) & (f.y >= 70) & (f.y < 84), C('stone', 1))
    f.put((f.x >= 234) & (f.x < 300) & (f.y >= 66) & (f.y < 71), C('stone', 3))
    f.put((f.x >= 234) & (f.x < 300) & (f.y >= 66) & (f.y < 67), C('stone', 4))
    f.poly([(270, 66), (278, 66), (275, 71), (268, 71)], C('cloth_sky', 3))   # 断口
    return f


def bg_indoor():
    """修道院：石拱 + 烛台。"""
    f = FX(BW, BH)
    ST = PAL['stone']
    f.put(f.y >= 0, ST[1])
    # 墙砖
    for y in range(0, 96, 7):
        off = 0 if (y // 7) % 2 == 0 else 6
        f.put((f.y >= y) & (f.y < y + 1), ST[0])
        for x in range(-off, BW, 12):
            f.put((f.x >= x) & (f.x < x + 1) & (f.y >= y) & (f.y < y + 7), ST[0])
    # 石拱（三个大拱门，拱内更暗）
    for cx in (53, 160, 267):
        r = 30
        m = ((f.x - cx) ** 2 + (f.y - 40) ** 2 <= r * r) | ((np.abs(f.x - cx) < r) & (f.y >= 40) & (f.y < 96))
        f.put(m, INK2)
        inner = ((f.x - cx) ** 2 + (f.y - 42) ** 2 <= (r - 6) ** 2) | ((np.abs(f.x - cx) < r - 6) & (f.y >= 42) & (f.y < 96))
        f.put(inner, PAL['cloth_black'][2])
        # 拱券石
        ring = m & ~(((f.x - cx) ** 2 + (f.y - 40) ** 2 <= (r - 3) ** 2) | ((np.abs(f.x - cx) < r - 3) & (f.y >= 40)))
        f.put(ring & (f.y < 96), ST[3])
        for a in np.linspace(math.pi, 2 * math.pi, 9):
            f.line((cx + math.cos(a) * (r - 3), 40 + math.sin(a) * (r - 3)), (cx + math.cos(a) * r, 40 + math.sin(a) * r),
                   ST[1])
        # 窗光
        f.put((np.abs(f.x - cx) < 4) & (f.y > 20) & (f.y < 44), C('magic_blue', 1))
        f.put((np.abs(f.x - cx) < 1) & (f.y > 20) & (f.y < 44), ST[1])
        f.disk(cx, 20, 4, C('magic_blue', 1))
    # 柱子
    for x in (0, 107, 213, 319):
        f.put((np.abs(f.x - x) < 7) & (f.y < 96), ST[2])
        f.put((f.x > x - 7) & (f.x < x - 4) & (f.y < 96), ST[3])
        f.put((f.x > x + 4) & (f.x < x + 7) & (f.y < 96), ST[1])
        f.put((np.abs(f.x - x) < 9) & (f.y > 90) & (f.y < 96), ST[3])
    # 烛台
    for x in (26, 80, 133, 187, 240, 294):
        f.put((np.abs(f.x - x) < 1) & (f.y > 60) & (f.y < 92), C('gold', 2))
        f.put((np.abs(f.x - x) < 4) & (f.y > 90) & (f.y < 92), C('gold', 2))
        f.put((np.abs(f.x - x) < 4) & (f.y > 59) & (f.y < 61), C('gold', 3))
        for dx in (-3, 0, 3):
            f.put((np.abs(f.x - x - dx) < 0.6) & (f.y > 55) & (f.y < 59), C('cloth_white', 3))
            f.ell(x + dx, 53.5, 0.9, 1.8, C('fire', 3))
            f.pix(x + dx, 53, C('fire', 4))
        f.disk(x, 54, 9, C('fire', 2), 0.12)
    # 石地板（透视横线）
    bands(f, 96, BH, [ST[2], ST[2], ST[3]], dither=False)
    for y in (100, 106, 114):
        f.put((f.y >= y) & (f.y < y + 1), ST[1])
    for x in range(-200, BW + 200, 24):
        f.line((BW / 2 + (x - BW / 2) * 0.55, 96), (x, BH), ST[1])
    return f


def bg_snow():
    f = FX(BW, BH)
    SN = PAL['snow']
    bands(f, 0, 70, [SN[0], SN[1], SN[1], SN[2]])
    mountains(f, 70, 40, 51, (SN[4], SN[2], SN[1]), snowcap=SN[4])
    mountains(f, 80, 18, 52, (SN[3], SN[2], SN[1]), jag=False)
    rs = rng(53)
    for i in range(26):
        x = rs.uniform(0, BW)
        pine(f, x, 90 + rs.uniform(-2, 2), 30 + rs.uniform(-4, 6), 14,
             (C('forest', 0), C('forest', 1), C('forest', 2)), trunk=C('wood', 0), snow=SN[4])
    bands(f, 90, BH, [SN[2], SN[3], SN[3], SN[4]])
    rs = rng(54)
    for i in range(120):
        x, y = rs.uniform(0, BW), rs.uniform(92, BH)
        f.pix(x, y, SN[2] if i % 2 else SN[4])
    # 风雪
    rs = rng(55)
    for i in range(140):
        x, y = rs.uniform(0, BW), rs.uniform(0, BH)
        if i % 4 == 0:
            f.line((x, y), (x - 2, y + 1), SN[4])
        else:
            f.pix(x, y, SN[4] if i % 3 else C('cloth_white', 4))
    return f


def bg_castle():
    """王城大厅：巨柱、旗帜、红地毯。"""
    f = FX(BW, BH)
    ST = PAL['stone']
    f.put(f.y >= 0, ST[1])
    # 高窗光
    for cx in (53, 160, 267):
        f.put((np.abs(f.x - cx) < 10) & (f.y > 8) & (f.y < 50), C('cloth_navy', 1))
        f.disk(cx, 10, 10, C('cloth_navy', 1))
        f.put((np.abs(f.x - cx) < 8) & (f.y > 10) & (f.y < 48), C('cloth_sky', 1))
        f.disk(cx, 11, 8, C('cloth_sky', 1))
        f.put((np.abs(f.x - cx) < 1) & (f.y > 4) & (f.y < 48), ST[2])
        f.put((np.abs(f.x - cx) < 8) & (np.abs(f.y - 28) < 0.6), ST[2])
    # 旗帜
    for cx in (53, 160, 267):
        f.put((np.abs(f.x - cx) < 9) & (f.y > 52) & (f.y < 84), C('cloth_crimson', 3))
        f.poly([(cx - 9, 84), (cx + 9, 84), (cx, 90)], C('cloth_crimson', 3))
        f.put((np.abs(f.x - cx) < 9) & (f.y > 52) & (f.y < 84) & (f.x > cx + 5), C('cloth_crimson', 2))
        f.put((np.abs(f.x - cx) < 10) & (f.y > 50) & (f.y < 53), C('gold', 3))
        f.put((np.abs(f.x - cx + 7) < 0.6) & (f.y > 53) & (f.y < 84), C('gold', 2))
        f.put((np.abs(f.x - cx - 7) < 0.6) & (f.y > 53) & (f.y < 84), C('gold', 2))
        # 白鹿纹章（简化）
        for dx, dy in ((-2, -3), (2, -3), (-1, -2), (1, -2), (0, -1), (0, 0), (-1, 1), (1, 1), (0, 2)):
            f.pix(cx + dx, 68 + dy, C('cloth_white', 4))
    # 巨柱
    for x in (0, 107, 213, 319):
        f.put((np.abs(f.x - x) < 10) & (f.y < 98), ST[3])
        f.put((f.x > x - 10) & (f.x < x - 6) & (f.y < 98), ST[4])
        f.put((f.x > x + 5) & (f.x < x + 10) & (f.y < 98), ST[2])
        for yy in (6, 90):
            f.put((np.abs(f.x - x) < 13) & (f.y > yy) & (f.y < yy + 6), ST[3])
            f.put((np.abs(f.x - x) < 13) & (f.y > yy) & (f.y < yy + 1), ST[4])
        f.put((np.abs(f.x - x - 2) < 0.6) & (f.y < 98), ST[2])
    # 地板 + 红地毯
    bands(f, 98, BH, [ST[2], ST[3]], dither=False)
    for y in (101, 107, 115):
        f.put((f.y >= y) & (f.y < y + 1), ST[1])
    CP = PAL['carpet']
    f.poly([(0, 104), (BW, 104), (BW, BH), (0, BH)], CP[3])
    f.put((f.y >= 104) & (f.y < 106), C('gold', 3))
    f.put((f.y >= 106) & (f.y < 107), CP[2])
    return f


def bg_fort():
    """要塞城墙：城垛、塔楼、城门。"""
    f = FX(BW, BH)
    bands(f, 0, 64, [C('cloth_sky', 1), C('cloth_sky', 2), C('cloth_sky', 3)])
    cloud(f, 40, 16, 50, (C('cloth_sky', 3), C('cloth_sky', 4), C('cloth_white', 3)), 8)
    cloud(f, 220, 24, 60, (C('cloth_sky', 3), C('cloth_sky', 4), C('cloth_white', 3)), 9)
    ST = PAL['stone']
    wall_top = 40
    f.put((f.y >= wall_top) & (f.y < 96), ST[2])
    # 砖缝
    for y in range(wall_top + 2, 96, 6):
        off = 0 if (y // 6) % 2 == 0 else 5
        f.put((f.y >= y) & (f.y < y + 1), ST[1])
        for x in range(-off, BW, 10):
            f.put((f.x >= x) & (f.x < x + 1) & (f.y >= y) & (f.y < y + 6), ST[1])
    # 城垛
    for x in range(0, BW, 14):
        f.put((f.x >= x) & (f.x < x + 8) & (f.y >= wall_top - 6) & (f.y < wall_top), ST[3])
        f.put((f.x >= x) & (f.x < x + 8) & (f.y >= wall_top - 6) & (f.y < wall_top - 5), ST[4])
    f.put((f.y >= wall_top) & (f.y < wall_top + 1), ST[4])
    # 塔楼
    for x in (46, 262):
        f.put((np.abs(f.x - x) < 18) & (f.y >= 14) & (f.y < 96), ST[3])
        f.put((f.x > x - 18) & (f.x < x - 14) & (f.y >= 14) & (f.y < 96), ST[4])
        f.put((f.x > x + 14) & (f.x < x + 18) & (f.y >= 14) & (f.y < 96), ST[1])
        for xx in range(x - 18, x + 18, 9):
            f.put((f.x >= xx) & (f.x < xx + 5) & (f.y >= 8) & (f.y < 14), ST[3])
        f.put((np.abs(f.x - x) < 2) & (f.y >= 30) & (f.y < 40), INK2)
        f.poly([(x + 2, 0), (x + 2, 8), (x + 14, 4)], C('team_red', 3))
        f.put((np.abs(f.x - x - 1.5) < 0.6) & (f.y < 14), C('wood', 1))
    # 城门
    gx = 160
    f.put((np.abs(f.x - gx) < 20) & (f.y > 58) & (f.y < 96), ST[1])
    f.disk(gx, 60, 20, ST[1])
    f.put((np.abs(f.x - gx) < 16) & (f.y > 60) & (f.y < 96), C('wood', 1))
    f.disk(gx, 61, 16, C('wood', 1))
    for xx in range(gx - 14, gx + 16, 5):
        f.put((f.x >= xx) & (f.x < xx + 1) & (f.y > 46) & (f.y < 96), C('iron', 1))
    for yy in (66, 78, 90):
        f.put((np.abs(f.x - gx) < 16) & (f.y >= yy) & (f.y < yy + 1), C('iron', 1))
    # 地面
    bands(f, 96, BH, [C('earth', 2), C('earth', 3), C('rock', 3)])
    rs = rng(61)
    for i in range(160):
        f.pix(rs.uniform(0, BW), rs.uniform(97, BH), C('rock', 2 + (i % 3 == 0) * 2))
    return f


# ================================================================ 站台
def platform(kind):
    """100x20：顶面椭圆（y≈0~10）+ 正面厚度（y≈6~18）。锚点 [50,4]。"""
    f = FX(PW, PH)
    styles = {
        'grass': (PAL['grass'], PAL['earth'], 'tuft'),
        'forest': (PAL['forest'], PAL['earth'], 'leaf'),
        'road': (PAL['earth'], PAL['rock'], 'pebble'),
        'stone': (PAL['stone'], PAL['stone'], 'tile'),
        'wood': (PAL['wood'], PAL['wood'], 'plank'),
        'snow': (PAL['snow'], PAL['rock'], 'snow'),
    }
    top, side, tex = styles[kind]
    cx = 50
    # 正面（侧壁）
    body = ((f.x - cx) / 49.5) ** 2 + ((f.y - 9.5) / 8.5) ** 2 <= 1.0
    body &= f.y >= 5
    if kind == 'wood':
        f.put(body, side[1])
        f.put(body & (f.y > 12), side[0])
    elif kind == 'stone':
        f.put(body, side[1])
        f.put(body & (f.y > 13), side[0])
    else:
        f.put(body, side[2])
        f.put(body & (f.y > 11), side[1])
        f.put(body & (f.y > 15), side[0])
    # 顶面
    topm = ((f.x - cx) / 49.5) ** 2 + ((f.y - 5.0) / 5.0) ** 2 <= 1.0
    n = len(top)
    base_i = {'grass': 3, 'forest': 3, 'road': 3, 'stone': 3, 'wood': 3, 'snow': 3}[kind]
    f.put(topm, top[base_i])
    # 顶面明暗：后缘亮（受光）、前缘暗
    f.put(topm & (f.y < 2.5), top[min(n - 1, base_i + 1)])
    f.put(topm & (f.y > 7.5), top[base_i - 1])
    edge = topm & ~(((f.x - cx) / 48.0) ** 2 + ((f.y - 5.0) / 4.0) ** 2 <= 1.0)
    f.put(edge & (f.y > 5), top[base_i - 2])
    rs = rng(hash(kind) % 1000)
    if tex == 'tuft' or tex == 'leaf':
        for i in range(70):
            x, y = rs.uniform(4, 96), rs.uniform(1.5, 9.5)
            if ((x - cx) / 48.0) ** 2 + ((y - 5.0) / 4.5) ** 2 > 1.0:
                continue
            f.line((x, y), (x + 0.5, y - 1.5), top[base_i + 1] if i % 2 else top[base_i - 1])
        if tex == 'leaf':
            for i in range(10):
                x, y = rs.uniform(10, 90), rs.uniform(2, 9)
                f.pix(x, y, PAL['leather'][3] if i % 2 else PAL['gold'][2])
        # 前缘垂下的草
        for x in range(4, 97, 3):
            yb = 5.0 + 5.0 * math.sqrt(max(0.0, 1 - ((x - cx) / 49.5) ** 2))
            f.line((x, yb - 1), (x + 0.5, yb + 1.5), top[base_i - 1])
    elif tex == 'pebble':
        for i in range(45):
            x, y = rs.uniform(6, 94), rs.uniform(1.5, 9.5)
            if ((x - cx) / 48.0) ** 2 + ((y - 5.0) / 4.5) ** 2 > 1.0:
                continue
            f.pix(x, y, side[2] if i % 2 else top[1])
        f.put(topm & (np.abs(f.y - 5) < 1.2) & (((np.floor(f.x) // 7) % 2) == 0), top[base_i + 1])
    elif tex == 'tile':
        for x in range(8, 96, 12):
            f.line((x, 0.5), (x + (x - cx) * 0.12, 10), top[1])
        f.put(topm & (np.abs(f.y - 5.0) < 0.6), top[1])
        # 侧面砖缝
        seams = np.zeros((PH, PW), bool)
        for x in range(6, 96, 10):
            seams |= (np.abs(f.x - x - 0.5) < 0.5) & (f.y > 11)
        f.put(seams & body, side[0])
        f.put(body & (np.abs(f.y - 13.5) < 0.6), side[0])
    elif tex == 'plank':
        for y in (2.0, 4.5, 7.0, 9.5):
            f.put(topm & (np.abs(f.y - y) < 0.5), top[1])
        for x in range(6, 96, 16):
            f.line((x, 1), (x, 3), top[1])
            f.line((x + 8, 5), (x + 8, 7), top[1])
        # 桥面前缘的横梁
        f.put(body & (f.y > 11) & (f.y < 13), side[2])
        for x in range(8, 96, 14):
            f.put(body & (np.abs(f.x - x) < 1) & (f.y > 12), side[0])
    elif tex == 'snow':
        for i in range(30):
            x, y = rs.uniform(6, 94), rs.uniform(1.5, 9.5)
            if ((x - cx) / 48.0) ** 2 + ((y - 5.0) / 4.5) ** 2 > 1.0:
                continue
            f.pix(x, y, top[2])
        # 积雪垂边
        for x in range(4, 97, 5):
            yb = 5.0 + 5.0 * math.sqrt(max(0.0, 1 - ((x - cx) / 49.5) ** 2))
            f.ell(x, yb + 0.5, 2.2, 1.6, top[3])
    # 外轮廓（底部暗边）
    solid = f.a[..., 3] > 0.5
    d = solid.copy()
    d[1:] |= solid[:-1]
    d[:, 1:] |= solid[:, :-1]
    d[:, :-1] |= solid[:, 1:]
    f.put(d & ~solid & (f.y > 6), INK2)
    return f


# ================================================================ 打包
def generate(assets_dir, prev_dir):
    os.makedirs(prev_dir, exist_ok=True)
    bgs = [('plains', bg_plains), ('forest', bg_forest), ('village', bg_village), ('bridge', bg_bridge),
           ('indoor', bg_indoor), ('snow', bg_snow), ('castle', bg_castle), ('fort', bg_fort)]
    plats = ['grass', 'road', 'stone', 'wood', 'snow', 'forest']
    cols = 2
    rows = (len(bgs) + cols - 1) // cols
    sheet_w = BW * cols
    plat_y = rows * BH
    sheet_h = plat_y + PH * 2
    sheet = np.zeros((sheet_h, sheet_w, 4), np.uint8)
    frames = {}
    for i, (name, fn) in enumerate(bgs):
        img = fn().img()
        img[..., 3] = 255
        img = snap_palette(img, BG_PAL)
        r, c = divmod(i, cols)
        sheet[r * BH:(r + 1) * BH, c * BW:(c + 1) * BW] = img
        frames['bg_' + name] = [c * BW, r * BH, BW, BH, 0, 0]
    for i, name in enumerate(plats):
        img = platform(name).img()
        solid = img[..., 3] > 0
        img[solid, 3] = 255
        img = snap_palette(img, BG_PAL)
        r, c = divmod(i, 6)
        x = c * PW
        y = plat_y + r * PH
        sheet[y:y + PH, x:x + PW] = img
        frames['plat_' + name] = [x, y, PW, PH, 50, 4]
    Image.fromarray(sheet, 'RGBA').save(os.path.join(assets_dir, 'battle_bg.png'), optimize=True)
    meta = dict(frames=frames, anims={},
                info=dict(bg_size=[BW, BH], plat_size=[PW, PH], plat_anchor=[50, 4],
                          note='背景左上角对齐屏幕 (0,0)；站台锚点为顶面中心，角色脚底锚点对准它。'))
    with open(os.path.join(assets_dir, 'battle_bg.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, separators=(',', ':'))
    Image.fromarray(sheet, 'RGBA').resize((sheet_w * 2, sheet_h * 2), Image.NEAREST).save(
        os.path.join(prev_dir, 'bg_sheet.png'))
    print('battle_bg: %d 背景 + %d 站台，图集 %dx%d' % (len(bgs), len(plats), sheet_w, sheet_h))
