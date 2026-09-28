# -*- coding: utf-8 -*-
"""
《灰烬王冠》剧情背景 / 标题画面 / Logo / 网页图标 生成脚本（纯 PIL + numpy，离线出 1 倍像素 PNG）。

用法
  python tools/art/gen_backgrounds.py                  # 生成全部
  python tools/art/gen_backgrounds.py festival chapel  # 只生成指定背景（也可写 title / logo / icon）
  python tools/art/gen_backgrounds.py --no-preview     # 不输出预览

输出
  assets/bg/{id}.png            剧情背景 320×180（不透明）
  assets/bg/index.json          背景 id 清单（含中文说明）
  assets/title_bg.png           标题画面背景 320×180
  assets/title_embers.png/.json 标题画面叠加用余烬粒子小图（精灵表 + 元数据）
  assets/logo.png               「灰烬王冠」Logo（透明底）
  assets/icon.png               32×32 王冠图标（favicon）
预览
  tools/art/preview/backgrounds/
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgkit import *  # noqa: F401,F403,E402
import bgkit as K  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT_BG = os.path.join(ROOT, 'assets', 'bg')
OUT_ASSETS = os.path.join(ROOT, 'assets')
PREV = os.path.join(HERE, 'preview', 'backgrounds')

SCENES = {}
DESC = {}


def scene(desc):
    def deco(fn):
        sid = fn.__name__[3:]
        SCENES[sid] = fn
        DESC[sid] = desc
        return fn
    return deco


# ===========================================================================
# 共用小部件
# ===========================================================================
def lantern(cv, x, y, body='roof_red:3', lit='fire:3', dark='roof_red:1', cap='INK'):
    """纸灯笼（4×5）：顶盖 + 发光灯身 + 下穗。"""
    x, y = int(x), int(y)
    cv.dot(x + 1, y, cap)
    cv.dot(x + 2, y, cap)
    for j in range(1, 4):
        for i in range(4):
            c = body
            if i == 0 or i == 3:
                c = dark if j != 2 else body
            if (i == 1 or i == 2) and j in (1, 2):
                c = lit
            cv.dot(x + i, y + j, c)
    cv.dot(x + 1, y + 4, cap)
    cv.dot(x + 2, y + 4, cap)
    cv.dot(x + 1, y + 5, dark)


def catenary(x0, y0, x1, y1, sag, n=None):
    n = n or int(abs(x1 - x0)) + 1
    pts = []
    for i in range(n + 1):
        s = i / n
        x = x0 + (x1 - x0) * s
        y = y0 + (y1 - y0) * s + sag * 4 * s * (1 - s)
        pts.append((x, y))
    return pts


def draw_polyline(cv, pts, col):
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        steps = int(max(abs(xb - xa), abs(yb - ya))) + 1
        for k in range(steps + 1):
            s = k / steps
            cv.dot(xa + (xb - xa) * s, ya + (yb - ya) * s, col)


def lit_windows(cv, wins, mask, cols=('fire:2', 'fire:3'), seed=0, frac=0.8, dark='INK'):
    rng = np.random.default_rng(seed)
    for (x, y, w, h) in wins:
        if not (0 <= x < cv.w and 0 <= y < cv.h) or not mask[min(cv.h - 1, y), min(cv.w - 1, x)]:
            continue
        on = rng.random() < frac
        for j in range(h):
            for i in range(w):
                if on:
                    cv.dot(x + i, y + j, cols[1] if j == 0 and h > 1 else cols[0])
                else:
                    cv.dot(x + i, y + j, dark)


def rim_edges(m, mode='ul'):
    """轮廓光像素：ul=左上光（顶边去掉朝右的斜坡 + 左边）；top=所有顶边（逆光）。"""
    top = edge(m, 0, -1)
    if mode == 'top':
        return top, np.zeros_like(m)
    if mode == 'ur':
        return top & ~edge(m, -1, 0), edge(m, 1, 0) & ~top
    return top & ~edge(m, 1, 0), edge(m, -1, 0) & ~top


def draw_castle(cv, cs, body, roof, t_body, t_roof=None, rim=None, rim2=None, mode='ul',
                warm=None, body_w=None, roof_w=None, texture=0.0, seed=0, skip=()):
    """按部件（远→近）给白鹿城上色：塔身圆柱明暗、屋顶左亮右暗、每个部件自带轮廓光。
    warm 场 + body_w/roof_w：下方暖光（节庆/火光）与上方冷光双光源。"""
    tex = fbm2d(cv.w, cv.h, 3, 2, seed, 2) * texture if texture else 0.0
    for i, p in enumerate(cs['parts']):
        if i in skip:
            continue
        m = p['m']
        u = np.clip((cv.xx - p['x0']) / max(1.0, p['x1'] - p['x0']), 0, 1)
        if p['type'] == 'body':
            sh = np.where(u < 0.34, 0.1, np.where(u > 0.7, -0.12, 0.0)) if p['cyl'] else 0.0
            t = t_body + sh + tex
            ra, rb = body, body_w
        else:
            sh = np.where(u < 0.5, 0.12, -0.12)
            t = (t_roof if t_roof is not None else t_body) + sh
            ra, rb = roof, roof_w
        if warm is not None and rb is not None:
            cv.ramp2(m, t, ra, rb, warm)
        else:
            cv.ramp(m, t, ra)
        r1, r2 = rim_edges(m, mode)
        if rim:
            cv.fill(r1, rim)
        if rim2:
            cv.fill(r2, rim2)


def bunting(cv, pts, cols, every=5, start=2):
    """彩旗串：沿线每隔 every 像素挂一面 3 宽的小三角旗。"""
    k = 0
    for i in range(start, len(pts) - 2, every):
        x, y = pts[i]
        c = cols[k % len(cols)]
        k += 1
        x, y = int(round(x)), int(round(y))
        for dx in range(3):
            cv.dot(x - 1 + dx, y + 1, c)
        cv.dot(x, y + 2, c)
        cv.dot(x, y + 3, c) if k % 2 else None


def town_rooftops(cv, y_base, seed, x0=0, x1=320, hmin=10, hmax=22, wmin=14, wmax=28):
    """一排城镇屋顶剪影（山墙 + 平顶 + 烟囱 + 尖塔混合）。返回 (遮罩, 窗户列表)。"""
    rng = np.random.default_rng(seed)
    mm = Mask(cv.w, cv.h, 4)
    wins = []
    x = x0 - rng.uniform(0, 10)
    while x < x1:
        w = rng.uniform(wmin, wmax)
        hh = rng.uniform(hmin, hmax)
        top = y_base - hh
        kind = rng.random()
        mm.rect(int(x), int(top), int(x + w), cv.h - 1)
        if kind < 0.55:
            rh = w * rng.uniform(0.35, 0.55)
            mm.poly([(x - 1, top + 1), (x + w / 2, top - rh), (x + w + 1, top + 1)])
        elif kind < 0.8:
            rh = rng.uniform(4, 7)
            mm.poly([(x - 1, top + 1), (x + 3, top - rh), (x + w - 3, top - rh), (x + w + 1, top + 1)])
        if rng.random() < 0.35:
            cx = x + rng.uniform(3, w - 5)
            mm.rect(int(cx), int(top - rng.uniform(6, 10)), int(cx + 2), int(top))
        # 窗
        for _ in range(int(rng.integers(1, 4))):
            wx = int(x + rng.uniform(2, max(3, w - 3)))
            wy = int(top + rng.uniform(3, max(4, hh - 3)))
            wins.append((wx, wy, 1 + int(rng.random() < 0.4), 2))
        x += w + rng.uniform(-3, 2)
    return mm.get(), wins


# ===========================================================================
# 1. 丰收祭之夜
# ===========================================================================
@scene('序章：白鹿城丰收祭之夜（城堡、灯笼、烟火）')
def bg_festival():
    cv = Canvas()
    cv.light = vignette(cv, 0.14)
    # 烟花光（让附近夜空亮一档）
    bursts = [(112, 30, 21, ['gold:1', 'gold:2', 'gold:3', 'fire:3', 'gold:4', 'fire:4'], 11),
              (214, 22, 16, ['hair_red:1', 'hair_red:2', 'roof_red:3', 'hair_red:4', 'team_red:5'], 12),
              (268, 54, 11, ['magic_blue:1', 'magic_blue:2', 'magic_blue:3', 'magic_blue:4'], 13),
              (52, 50, 10, ['team_green:2', 'team_green:3', 'team_green:4', 'team_green:5'], 14)]
    glow = np.zeros_like(cv.light)
    for (bx, by, r, _, _) in bursts:
        glow = np.maximum(glow, radial(cv, bx, by, r * 1.9) * 0.22)
    cv.light += glow
    # 夜空
    sky = rp('night:0', 'night:1', 'night:2', 'night:3', 'night:4', 'dusk:2', 'dusk:3', 'dusk:4')
    t = np.clip(vgrad(cv, -10, 128), 0, 1) ** 1.25
    cv.ramp(None, t, sky, soft=0.55)
    stars(cv, cv.full(), 70, 3, ymax=100, bias=1.6)
    for (bx, by, r, cols, sd) in bursts:
        firework(cv, bx, by, r, cols, sd, rays=18 if r > 15 else 12)

    # 远山（城堡所在山丘两侧）
    hill = height_mask(ridge_line(cv.w, 104, 10, 60, 5, 3))
    cv.ramp(hill, 0.25 + 0.5 * np.clip(vgrad(cv, 90, 125), 0, 1), rp('night:1', 'night:2', 'dusk:1', 'dusk:2'), soft=0.6)

    # 城堡（白鹿城）：上方月光冷色、下方节庆暖光
    cs = royal_castle(160, 106, s=0.76)
    m = cs['mask']
    t_body = 0.36 + 0.4 * np.clip(vgrad(cv, 62, 106), 0, 1) ** 1.6
    warm = np.clip(vgrad(cv, 66, 100), 0, 1)
    draw_castle(cv, cs,
                body=rp('INK', 'night:1', 'night:2', 'night:3', 'stone:2', 'stone:3'),
                body_w=rp('INK', 'INK2', 'dusk:2', 'dusk:3', 'dusk:5', 'dusk:6'),
                roof=rp('INK', 'roof_blue:0', 'roof_blue:1', 'roof_blue:2', 'roof_blue:3', 'roof_blue:4'),
                t_body=t_body, t_roof=0.42, rim='night:6', rim2='night:5', warm=warm,
                roof_w=rp('INK', 'roof_blue:0', 'roof_blue:1', 'roof_blue:2', 'roof_blue:3', 'roof_blue:4'))
    lit_windows(cv, cs['windows'], m, seed=4, frac=0.9)
    gx0, gy0, gx1, gy1 = cs['gate']
    cv.fill(rect_mask(gx0, gy0 + 2, gx1, gy1) | rect_mask(gx0 + 1, gy0 + 1, gx1 - 1, gy1), 'fire:2')
    cv.fill(rect_mask(gx0 + 1, gy0 + 3, gx1 - 1, gy1), 'fire:3')
    # 城墙上的长幅白鹿旗
    for bx in (133, 147, 173, 187):
        for j in range(9):
            for i in range(3):
                c = 'cloth_navy:3' if i else 'cloth_navy:4'
                if j == 8 and i == 1:
                    continue
                cv.dot(bx + i, 76 + j, c)
        cv.dot(bx + 1, 79, 'cloth_white:4')
        cv.dot(bx + 1, 80, 'cloth_white:3')
        cv.dot(bx, 78, 'cloth_white:3')
        cv.dot(bx + 2, 78, 'cloth_white:3')
        for i in range(3):
            cv.dot(bx + i, 76, 'gold:3')
    for (tx, ty) in cs['tips']:
        flag(cv, tx, ty, 'cloth_white:3', 'cloth_sky:3', length=4, height=2, pole='night:2', pole_h=3)

    # 城镇屋顶
    roofs, wins = town_rooftops(cv, 120, 21, hmin=8, hmax=16, wmin=12, wmax=22)
    cv.ramp(roofs, 0.2 + 0.4 * np.clip(vgrad(cv, 100, 130), 0, 1), rp('INK', 'INK2', 'night:1', 'dusk:1'), soft=0.5)
    cv.fill(rim(roofs, ((0, -1),)), 'dusk:3')
    lit_windows(cv, wins, roofs, seed=8, frac=0.85)
    # 街上暖光（屋顶之间的缝）
    # 灯笼串
    for (x0, y0, x1, y1, sag, n) in [(-6, 10, 118, 6, 18, 9), (196, 4, 330, 16, 16, 9)]:
        pts = catenary(x0, y0, x1, y1, sag)
        draw_polyline(cv, pts, 'INK2')
        bunting(cv, pts, ['gold:3', 'cloth_white:3', 'roof_red:3', 'cloth_sky:3'], every=6, start=5)
        for k in range(1, n):
            p = pts[int(len(pts) * k / n)]
            lantern(cv, p[0] - 1.5, p[1] + 1)
    # 近景：城下人群剪影（底部安静）
    crowd = height_mask(128 + fbm1d(cv.w, 3, 31, 2) * 3 + (np.arange(cv.w) % 7 < 2) * 1.5)
    cv.fill(crowd, 'INK')
    return cv


# ===========================================================================
# 白鹿纹章 / 黑鹰纹章（小位图）
# ===========================================================================
DEER = [
    '.x.........x.',
    '.x.x.....x.x.',
    '.xx.......xx.',
    '..xx.....xx..',
    '...xx...xx...',
    '....xxxxx....',
    '...x.xxx.x...',
    '.....xxx.....',
    '.....xxx.....',
    '......x......',
]
EAGLE = [
    '......x......',
    '.....xxx.....',
    'x...xxxxx...x',
    'xx.xxxxxxx.xx',
    'xxxxxxxxxxxxx',
    '.xxxxxxxxxxx.',
    '..xx.xxx.xx..',
    '.....xxx.....',
    '....xx.xx....',
    '...x.....x...',
]


def stamp(cv, bmp, x, y, col, mask=None):
    for j, row in enumerate(bmp):
        for i, ch in enumerate(row):
            if ch == 'x':
                xx, yy = int(x) + i, int(y) + j
                if 0 <= xx < cv.w and 0 <= yy < cv.h and (mask is None or mask[yy, xx]):
                    cv.dot(xx, yy, col)


def hang_banner(cv, x0, y0, w, h, cloth, trim, emblem=None, emblem_col=None, burnt=0.0, seed=0, tail=True, t=None):
    """竖挂长旗：横杆 + 布面（左亮右暗）+ 金边 + 纹章；burnt>0 时下缘烧成锯齿。返回布面遮罩。"""
    rng = np.random.default_rng(seed)
    mm = Mask(cv.w, cv.h, 1)
    bottom = [y0 + h - (burnt * h * (0.3 + 0.7 * rng.random()) if burnt else 0) for _ in range(w)]
    pts = [(x0, y0)]
    for i in range(w):
        yb = bottom[i]
        if tail and not burnt:
            yb = y0 + h - abs(i - (w - 1) / 2.0) * 2.0 * (h * 0.18) / max(1, (w - 1) / 2.0)
        pts.append((x0 + i, yb))
    pts.append((x0 + w - 1, y0))
    for i in range(w):
        mm.rect(x0 + i, y0, x0 + i, int(round(pts[i + 1][1])))
    m = mm.get()
    u = (cv.xx - x0) / max(1, w - 1)
    tt = (0.62 - 0.35 * u) if t is None else t - 0.3 * u
    cv.ramp(m, tt, cloth, soft=0.4)
    cv.fill(m & ((cv.xx == x0) | (cv.xx == x0 + w - 1)), trim[1])
    cv.fill(m & (cv.xx == x0), trim[2] if len(trim) > 2 else trim[1])
    cv.fill(edge(m, 0, 1), trim[0])
    if emblem and emblem_col:
        ew = len(emblem[0])
        stamp(cv, emblem, x0 + (w - ew) // 2, y0 + max(3, h // 5), emblem_col, mask=m)
    # 横杆
    cv.fill(rect_mask(x0 - 2, y0 - 1, x0 + w + 1, y0), 'INK')
    cv.dot(x0 - 2, y0 - 2, trim[1])
    cv.dot(x0 + w + 1, y0 - 2, trim[1])
    return m


# ===========================================================================
# 王座厅（火海 / 黎明 / 加冕 三种状态共用同一个房间）
# ===========================================================================
VPX, VPY = 160, 56
BW0, BW1, BY = 98, 222, 90


def _left_floor_y(x):
    k = (x - VPX) / float(BW0 - VPX)
    return VPY + k * (BY - VPY)


def throne(cv, cx, base, gold, velvet, ink='INK', scorch=False):
    """王座：尖拱高背 + 鹿角纹饰 + 红丝绒 + 扶手。cx 中心，base 座脚底 y。"""
    x0, x1 = cx - 11, cx + 11
    top = base - 42
    mm = Mask(cv.w, cv.h, 4)
    mm.poly([(x0 + 2, top + 10), (cx, top), (x1 - 2, top + 10), (x1 - 2, base - 12), (x0 + 2, base - 12)])
    back = mm.get()
    arms = rect_mask(x0 - 1, base - 18, x1 + 1, base - 12) | rect_mask(x0 - 1, base - 12, x0 + 2, base) | rect_mask(x1 - 2, base - 12, x1 + 1, base)
    seat = rect_mask(x0 + 2, base - 12, x1 - 2, base - 8)
    frame = back | arms | seat
    cv.fill(outline(frame, diag=True), ink)
    u = (cv.xx - x0) / 22.0
    cv.ramp(frame, 0.75 - 0.5 * u, gold, soft=0.4)
    # 靠背内衬
    mi = Mask(cv.w, cv.h, 4)
    mi.poly([(x0 + 5, top + 12), (cx, top + 5), (x1 - 5, top + 12), (x1 - 5, base - 19), (x0 + 5, base - 19)])
    inner = mi.get()
    cv.ramp(inner, 0.7 - 0.45 * u - 0.25 * vgrad(cv, top, base - 18), velvet, soft=0.4)
    cv.fill(edge(inner, 0, -1) | edge(inner, -1, 0), gold[1])
    seatc = rect_mask(x0 + 3, base - 12, x1 - 3, base - 10)
    cv.ramp(seatc, 0.7 - 0.4 * u, velvet, soft=0.4)
    # 鹿角尖饰
    for sd in (-1, 1):
        ax = cx + sd * 9
        for k, (dx, dy) in enumerate([(0, 0), (0, -1), (sd, -2), (sd, -3), (0, -3), (-sd, -4)]):
            cv.dot(ax + dx, top + 8 + dy, gold[-1] if k > 2 else gold[-2])
    cv.dot(cx, top - 1, gold[-1])
    cv.dot(cx, top - 2, gold[-2])
    # 白鹿小徽
    stamp(cv, ['x.x', '.x.', '.x.'], cx - 1, top + 14, 'cloth_white:3')
    if scorch:
        n = fbm2d(cv.w, cv.h, 3, 3, 77, 2)
        cv.fill(frame & (n > 0.25) & (cv.t4 > 0.4), 'INK2')


def room_geometry(cv):
    left = poly_mask([(-1, -1), (BW0, -1), (BW0, BY), (-1, _left_floor_y(-1))])
    right = poly_mask([(BW1, -1), (320, -1), (320, _left_floor_y(-1)), (BW1, BY)])
    back = rect_mask(BW0, 0, BW1, BY - 1)
    floor = ~(left | right | back)
    return left, right, back, floor


def floor_uv(cv):
    k = np.maximum((cv.yy - VPY) / float(BY - VPY), 1e-3)
    u = (cv.xx - VPX) / k
    z = 10.0 / k
    return u, z, k


def side_wall_uv(cv):
    k = np.maximum(np.abs(cv.xx - VPX) / float(VPX - BW0), 1e-3)
    v = (cv.yy - VPY) / k
    z = 10.0 / k
    return v, z, k


def brick_lines(u, v, bw, bh):
    """砖缝：返回 (横缝, 竖缝) 布尔场。u 横向坐标，v 纵向坐标。"""
    row = np.floor(v / bh)
    hl = (v - row * bh) < 1.0
    uu = u + (row % 2) * bw / 2.0
    vl = (uu - np.floor(uu / bw) * bw) < 1.0
    return hl, vl


def pillar(cv, x0, x1, y_top, y_base, ramp, t_base, light_from=-1, cap=True):
    """方柱（正面）：左右明暗 + 柱础 + 柱头。"""
    m = rect_mask(x0, y_top, x1, y_base)
    u = (cv.xx - x0) / max(1.0, x1 - x0)
    sh = (0.5 - u) * 0.36 * (-light_from)
    cv.ramp(m, t_base + sh, ramp, soft=0.5)
    w = x1 - x0
    # 竖向凹槽
    for gx in (x0 + w * 0.33, x0 + w * 0.66):
        if w >= 8:
            cv.fill(m & (cv.xx == int(gx)) & (cv.yy > y_top + 4) & (cv.yy < y_base - 4), ramp[1])
    # 柱础
    bh = max(2, int(w * 0.25))
    base_m = rect_mask(x0 - 1, y_base - bh, x1 + 1, y_base)
    cv.ramp(base_m, t_base + sh + 0.05, ramp, soft=0.5)
    cv.fill(edge(base_m, 0, -1), ramp[min(len(ramp) - 1, 4)])
    cv.fill(rect_mask(x0 - 1, y_base + 1, x1 + 1, y_base + 1), 'INK')
    cv.fill(rect_mask(x0, y_top, x0, y_base) if light_from < 0 else rect_mask(x1, y_top, x1, y_base), ramp[4])
    cv.fill(rect_mask(x1, y_top, x1, y_base) if light_from < 0 else rect_mask(x0, y_top, x0, y_base), 'INK')
    return m


def smoke_band(cv, base_fn, seed, ramp, rmin=7, rmax=12, down=0.5, up=0.0, gain=0.3, top_t=0.08, from_top=True):
    """翻滚的烟带：上方连成一片（暗），下缘是一串相互重叠的烟团（底部受火光照亮）。
    base_fn(x) 给出该处烟带下缘的 y。from_top=False 时烟团向下堆（地面烟雾）。"""
    rng = np.random.default_rng(seed)
    items = []
    x = -12.0
    while x < cv.w + 12:
        r = rng.uniform(rmin, rmax)
        items.append((x, base_fn(x) - r * 0.7 + rng.uniform(-2, 2), r))
        x += r * rng.uniform(0.9, 1.3)
    body = np.zeros((cv.h, cv.w), bool)
    for (x, y, r) in items:
        if from_top:
            body |= (np.abs(cv.xx - x) <= r) & (cv.yy <= y)
    cv.ramp(body, top_t + 0.1 * np.clip(vgrad(cv, 0, 40), 0, 1), ramp, soft=0.6, gain=gain)
    order = sorted(items, key=lambda it: it[1])       # 靠上的先画，靠下（更近火光）的后画
    allm = body.copy()
    for (x, y, r) in order:
        m = ellipse_mask(x, y, r * 1.2, r)
        rel = np.clip((cv.yy - (y - r)) / (2.0 * r), 0, 1)
        t = 0.2 + down * rel ** 1.5 + up * (1 - rel) - 0.08 * np.clip((cv.xx - x) / r, -1, 1)
        cv.fill(edge(m, 0, -1) & allm & (cv.t4 > 0.3), ramp[0])
        cv.ramp(m, t, ramp, soft=0.6, gain=gain)
        allm |= m
    return allm


def streak_cloud(cv, x0, x1, y, th, seed, ramp, t0=0.3, lit=0.55, top_dark=0.12, rim_bottom=True):
    """横向霞云：一串压扁的椭圆、两端收细；下缘受光（色阶末端），上缘略暗。"""
    rng = np.random.default_rng(seed)
    mm = Mask(cv.w, cv.h, 4)
    L = float(x1 - x0)
    n = max(3, int(L / 7))
    for i in range(n + 1):
        s = i / float(n)
        cx = x0 + L * s + rng.uniform(-2, 2)
        taper = math.sin(math.pi * s) ** 0.7
        ry = max(0.7, th * taper * rng.uniform(0.55, 1.1))
        rx = rng.uniform(5, 9) * (0.6 + 0.4 * taper)
        cy = y + rng.uniform(-0.5, 0.5) * th * 0.7 - ry * 0.3
        mm.ellipse(cx, cy, rx, ry)
    m = mm.get()
    anyc = m.any(axis=0)
    top = np.where(anyc, np.argmax(m, axis=0), 0)
    bot = np.where(anyc, cv.h - 1 - np.argmax(m[::-1], axis=0), 0)
    rel = (cv.yy - top[None, :]) / np.maximum(1, bot - top)[None, :]
    t = t0 + lit * np.clip(rel, 0, 1) ** 1.6 - top_dark * (1 - rel)
    cv.ramp(m, t, ramp, soft=0.5, gain=0.3)
    if rim_bottom:
        cv.fill(edge(m, 0, 1), ramp[-1])
    return m


def puffs(cv, items, ramp, up=0.0, down=0.0, outline_col=None, gain=0.6):
    """团状烟云：一串圆（远→近），每团按竖直位置明暗；up>0 顶亮（天光），down>0 底亮（火光）。"""
    allm = np.zeros((cv.h, cv.w), bool)
    for (x, y, r) in items:
        m = ellipse_mask(x, y, r * 1.15, r)
        rel = np.clip((cv.yy - (y - r)) / (2.0 * r), 0, 1)        # 0 顶 → 1 底
        t = 0.35 + up * (1 - rel) + down * rel - 0.12 * np.clip((cv.xx - x) / r, -1, 1)
        if outline_col:
            cv.fill(outline(m) & ~allm, outline_col)
        cv.ramp(m, t, ramp, soft=0.6, gain=gain)
        allm |= m
    return allm


def throne_room(mode):
    cv = Canvas()
    fire, dawn, coro = mode == 'fire', mode == 'dawn', mode == 'coronation'
    left, right, back, floor = room_geometry(cv)
    L = vignette(cv, 0.16 if fire else 0.12)

    if fire:
        wall = rp('INK', 'smoke:1', 'smoke:2', 'roof_red:1', 'hair_red:2', 'roof_red:2', 'dusk:5', 'fire:2')
        flo = rp('INK', 'smoke:1', 'smoke:2', 'roof_red:1', 'roof_red:2', 'dusk:5', 'fire:2')
        pil = rp('INK', 'smoke:1', 'smoke:2', 'smoke:3', 'roof_red:2', 'dusk:5', 'fire:2', 'fire:3')
        glows = [(66, 108, 70, 0.55), (254, 108, 70, 0.55), (160, 40, 70, 0.3), (118, 40, 40, 0.3), (202, 40, 40, 0.3), (160, 100, 60, 0.25)]
    elif dawn:
        wall = rp('INK', 'stone:0', 'stone:1', 'stone:2', 'stone:3', 'dawn:5', 'dawn:6', 'dawn:7')
        flo = rp('INK', 'stone:0', 'stone:1', 'stone:2', 'stone:3', 'dawn:5', 'dawn:6', 'dawn:7')
        pil = rp('INK', 'stone:0', 'stone:1', 'stone:2', 'stone:3', 'stone:4', 'dawn:6', 'dawn:7')
        glows = []
    else:
        wall = rp('INK2', 'stone:1', 'stone:2', 'stone:3', 'stone:4', 'dawn:6', 'dawn:7', 'dawn:8')
        flo = rp('INK2', 'stone:1', 'stone:2', 'stone:3', 'stone:4', 'dawn:6', 'dawn:7', 'dawn:8')
        pil = rp('INK', 'stone:1', 'stone:2', 'stone:3', 'stone:4', 'stone:5', 'dawn:7', 'dawn:8')
        glows = []

    light = L.copy()
    for (gx, gy, r, s) in glows:
        light += radial(cv, gx, gy, r, 1.3) * s
    # 晨光光柱（从后墙高窗斜射向前下方，左上光源 → 光柱偏向右下）
    shafts = np.zeros_like(light)
    if dawn or coro:
        for (wx, wy, hw, s) in [(160, 24, 9, 1.0), (117, 40, 6, 0.8), (203, 40, 6, 0.8)]:
            dy = np.maximum(cv.yy - wy, 0)
            half = hw + dy * 0.2
            cxs = wx + dy * 0.34
            core = np.abs(cv.xx - cxs) < half
            soft_edge = np.abs(cv.xx - cxs) < half + 4
            fade = np.clip(1 - dy / 150.0, 0, 1) * (cv.yy > wy)
            shafts = np.maximum(shafts, (core * 1.0 + (soft_edge & ~core) * 0.5) * s * fade)
        light += shafts * (0.5 if dawn else 0.3)
    if coro:
        light += 0.08
    cv.light = light

    # ---- 后墙
    bl_h, bl_v = brick_lines(cv.xx - BW0, cv.yy, 14, 7)
    t = 0.3 + 0.1 * np.clip(vgrad(cv, 0, BY), 0, 1)
    cv.ramp(back, t - 0.12 * (bl_h | bl_v), wall, soft=0.5)
    # ---- 侧墙（透视砖缝）
    v, z, k = side_wall_uv(cv)
    hl, vl = brick_lines(z * 6, v, 9, 7)
    for sm in (left, right):
        cv.ramp(sm, 0.34 - 0.12 * (hl | vl) + 0.05 * (k - 1), wall, soft=0.5)
    # 墙角线
    cv.fill(edge(back, -1, 0) | edge(back, 1, 0), wall[1])
    # ---- 地面（透视方砖 + 红毯）
    u, zf, kf = floor_uv(cv)
    tile = ((np.floor(u / 18) + np.floor(zf)) % 2).astype(float)
    gl = ((u - np.floor(u / 18) * 18) < 1.2 * np.minimum(kf, 2)) | ((zf - np.floor(zf)) < 0.07 * kf)
    cv.ramp(floor, 0.3 + 0.07 * tile - 0.1 * gl, flo, soft=0.5)
    # 红毯
    carpet = floor & (np.abs(cv.xx - VPX) < 14 * kf) & (cv.yy > BY + 6)
    crp = rp('INK', 'carpet:0', 'carpet:1', 'carpet:2', 'carpet:3', 'carpet:4', 'fire:2' if fire else 'dawn:7')
    cv.ramp(carpet, 0.38 + 0.05 * kf, crp, soft=0.5)
    cv.fill(carpet & (np.abs(np.abs(cv.xx - VPX) - 12 * kf) < 0.7 * kf), 'gold:2' if not coro else 'gold:3')
    cv.fill(edge(carpet, -1, 0) | edge(carpet, 1, 0), 'INK')

    # ---- 高窗：中央圆窗 + 两侧尖拱窗
    def lancet(x0, y0, w, h):
        mm = Mask(cv.w, cv.h, 4)
        cx = x0 + w / 2.0
        mm.poly([(x0, y0 + w * 0.7), (cx - w * 0.25, y0 + w * 0.12), (cx, y0), (cx + w * 0.25, y0 + w * 0.12), (x0 + w, y0 + w * 0.7), (x0 + w, y0 + h), (x0, y0 + h)])
        return mm.get()
    wins = [lancet(108, 14, 18, 52), lancet(194, 14, 18, 52)]
    rose = ellipse_mask(160, 22, 17, 17)
    wm = wins[0] | wins[1] | rose
    # 窗框（厚石框）
    frame = dilate(wm, 2) & ~wm
    cv.ramp(frame, 0.45 + 0.1 * (cv.xx < VPX), pil, soft=0.5)
    cv.fill(outline(dilate(wm, 2)), 'INK')
    if fire:
        t = 1 - np.clip(vgrad(cv, 6, 70), 0, 1)
        cv.ramp(wm, 0.35 + 0.65 * (1 - t) * 0.9, rp('fire:0', 'fire:1', 'fire:2', 'fire:3', 'fire:4'), soft=0.7, gain=0)
        # 窗外燃烧的城市剪影
        city = height_mask(62 - (np.arange(320) % 11 < 4) * 6 - (np.arange(320) % 29 < 3) * 10) & wm
        cv.fill(city, 'fire:0')
    elif dawn:
        t = np.clip(vgrad(cv, 4, 66), 0, 1)
        cv.ramp(wm, 0.25 + 0.7 * t, rp('dawn:3', 'dawn:4', 'dawn:5', 'dawn:6', 'dawn:7', 'dawn:8'), soft=0.7, gain=0)
    else:
        t = np.clip(vgrad(cv, 4, 66), 0, 1)
        cv.ramp(wm, 0.4 + 0.6 * t, rp('day:3', 'day:4', 'day:5', 'day:6', 'dawn:7', 'dawn:8'), soft=0.7, gain=0)
    # 窗棂
    mull = np.zeros_like(wm)
    for (x0, w) in ((108, 18), (194, 18)):
        mull |= (cv.xx == x0 + w // 2) | ((cv.yy - 14) % 12 == 0)
    rr = np.sqrt((cv.xx - 160) ** 2 + (cv.yy - 22) ** 2)
    ang = np.arctan2(cv.yy - 22, cv.xx - 160)
    spokes = (np.abs(((ang / (2 * np.pi) * 8) % 1) - 0.5) > 0.44) & (rr > 4)
    mull |= (rose & ((np.abs(rr - 8) < 0.8) | spokes | (rr < 2.5)))
    if dawn:
        # 破碎：窗棂残缺 + 残余碎玻璃
        n = fbm2d(cv.w, cv.h, 5, 5, 9, 2)
        cv.fill(wm & mull & (n > -0.1), 'INK')
        shard = wm & (dilate(frame, 2)) & (n > 0.05) & ~mull
        cv.fill(shard & (cv.t4 > 0.3), 'glass_b:2')
        cv.fill(shard & (cv.t4 <= 0.3), 'glass_r:2')
    elif fire:
        cv.fill(wm & mull, 'INK')
    else:
        cv.fill(wm & mull & ~rose, 'INK')
        # 修复后的彩色玻璃圆窗
        pal = ['glass_b:2', 'glass_r:2', 'glass_y:2', 'glass_g:2', 'glass_b:3', 'glass_v:2']
        seg = np.floor(((ang / (2 * np.pi)) % 1) * 8).astype(int)
        for i in range(8):
            cv.fill(rose & ~mull & (seg == i) & (rr >= 8), pal[i % len(pal)])
        cv.fill(rose & ~mull & (rr < 8), 'glass_y:3')
        cv.fill(rose & mull, 'INK')

    # ---- 王座两侧的长旗
    banner_ms = []
    for i, bx in enumerate((131, 179)):
        if fire:
            bm = hang_banner(cv, bx, 30, 11, 38, rp('cloth_navy:0', 'cloth_navy:1', 'cloth_navy:2', 'cloth_navy:3', 'cloth_navy:4'),
                             ['gold:1', 'gold:2', 'gold:3'], ['x.x', '.x.', '.x.'], 'cloth_white:2', burnt=0.3 + 0.2 * i, seed=5 + i)
        elif dawn:
            bm = hang_banner(cv, bx, 30, 11, 38, rp('INK', 'cloth_navy:0', 'cloth_navy:1', 'cloth_navy:2'),
                             ['INK2', 'gold:1', 'gold:1'], None, None, burnt=0.5 + 0.15 * i, seed=6 + i)
        else:
            bm = hang_banner(cv, bx, 30, 11, 40, rp('cloth_navy:1', 'cloth_navy:2', 'cloth_navy:3', 'cloth_navy:4', 'cloth_sky:3'),
                             ['gold:2', 'gold:3', 'gold:4'], ['x.x', '.x.', '.x.'], 'cloth_white:4', seed=7 + i)
        banner_ms.append(bm)

    # ---- 台阶
    steps = [(122, 198, 78, 82), (116, 204, 82, 86), (110, 210, 86, 90)]
    for i, (x0, x1, y0, y1) in enumerate(steps):
        m = rect_mask(x0, y0, x1, y1)
        cv.ramp(m, 0.36 + 0.03 * i, pil, soft=0.5)
        cv.fill(rect_mask(x0, y0, x1, y0), pil[5])
        cv.fill(rect_mask(x0, y1, x1, y1), pil[1])
        cm = m & (np.abs(cv.xx - VPX) < 13 + i)
        cv.ramp(cm, 0.42, crp, soft=0.5)
        cv.fill(cm & (cv.yy == y0), crp[4])
    top_step = rect_mask(128, 72, 192, 78)
    cv.ramp(top_step, 0.34, pil, soft=0.5)
    cv.fill(rect_mask(128, 72, 192, 72), pil[5])

    # ---- 王座
    gold = rp('gold:0', 'gold:1', 'gold:2', 'gold:3', 'gold:4')
    if fire:
        gold = rp('gold:0', 'gold:1', 'gold:2', 'gold:3', 'fire:4')
    throne(cv, 160, 77, gold, rp('carpet:0', 'carpet:1', 'carpet:2', 'carpet:3'), scorch=dawn)

    # ---- 立柱（远→近）
    for side in (-1, 1):
        for (xb, w, yb) in [(88, 7, 95), (60, 12, 110), (14, 24, 134)]:
            if side < 0:
                x0, x1 = xb - w // 2, xb + w // 2
            else:
                x0, x1 = 320 - xb - w // 2, 320 - xb + w // 2
            pillar(cv, x0, x1, -1, yb, pil, 0.36 + 0.06 * (w > 20), light_from=-1 if side < 0 else 1)
    if dawn:
        # 烟熏：墙脚与柱脚向上渐淡的黑灰，窗口上沿的熏痕
        soot = (np.clip(vgrad(cv, 40, 96), 0, 1) ** 1.5) * (1 - floor) * 0.9
        n = fbm2d(cv.w, cv.h, 10, 18, 5, 3)
        dais = rect_mask(104, 26, 216, 100)
        cv.fill((soot + n * 0.3 > cv.t8 + 0.35) & ~floor & (cv.light < 0.15) & ~dais, 'INK2')
        above = dilate(wm, 3) & ~dilate(wm, 2) & (cv.yy < 40) & (cv.t4 > 0.5)
        cv.fill(above, 'INK2')
    return cv, carpet


def fallen_banner(cv, pts, width, cloth, trim, seed=0):
    """倒在地上的长旗：沿折线铺开的布带。"""
    mm = Mask(cv.w, cv.h, 4)
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        mm.poly([(xa, ya), (xb, yb), (xb, yb + width), (xa, ya + width)])
    m = mm.get()
    cv.fill(outline(m), 'INK')
    cv.ramp(m, 0.5 - 0.3 * vgrad(cv, pts[0][1], pts[-1][1] + width), cloth, soft=0.5)
    cv.fill(edge(m, 0, -1), trim)
    return m


@scene('序章：王座厅陷入火海（王座、倒下的旗帜、火光）')
def bg_throne_fire():
    cv, carpet = throne_room('fire')
    # 倒下的旗帜（左侧，斜铺在台阶前）
    fb = fallen_banner(cv, [(84, 98), (104, 101), (126, 106), (142, 114)], 5,
                       rp('cloth_navy:0', 'cloth_navy:1', 'cloth_navy:2', 'cloth_navy:3'), 'gold:3')
    # 倒下的旗杆
    draw_polyline(cv, [(206, 92), (232, 112)], 'INK')
    draw_polyline(cv, [(207, 92), (233, 112)], 'wood:2')
    # 火焰：两侧墙脚、旗帜末端、后墙窗下
    for (x0, x1) in ((0, 100), (220, 320)):
        bed = rect_mask(x0, 131, x1, 134) & (fbm2d(cv.w, cv.h, 4, 2, x0 + 7, 2) + 0.2 > cv.t4 * 0.6)
        cv.fill(bed & (cv.t4 > 0.35), 'fire:1')
        cv.fill(bed & (cv.t4 <= 0.35), 'fire:0')
        cv.fill(rect_mask(x0, 132, x1, 132) & (cv.t4 > 0.6), 'fire:2')
    flames(cv, 0, 100, 132, 26, 60, 3, density=1.3)
    flames(cv, 220, 320, 132, 26, 60, 4, density=1.3)
    flames(cv, 70, 104, 104, 10, 24, 5, density=1.4)
    flames(cv, 214, 248, 104, 10, 26, 6, density=1.4)
    flames(cv, 132, 150, 115, 6, 16, 7, density=1.5)
    flames(cv, 100, 124, 92, 6, 14, 8, density=1.5)
    flames(cv, 196, 220, 92, 6, 14, 9, density=1.5)
    # 旗帜下缘的余火
    flames(cv, 148, 172, 64, 3, 8, 10, density=2.0)
    # 王冠滚落在台阶旁的火里
    cx, cy = 186, 101
    crown = ['x.x.x', 'xxxxx', 'xxxxx']
    stamp(cv, crown, cx, cy, 'gold:3')
    stamp(cv, ['x.x.x'], cx, cy, 'gold:4')
    cv.dot(cx + 2, cy + 1, 'hair_red:3')
    cv.fill(rect_mask(cx - 1, cy + 3, cx + 5, cy + 3), 'INK')
    flames(cv, 191, 198, 104, 4, 9, 11, density=2.0)
    # 天花板翻滚的浓烟（上方连片，下缘烟团被火映红；中间留出圆窗）
    smoke_band(cv, lambda x: 10 + (abs(x - 160) / 160.0) ** 1.4 * 30 - 9 * math.exp(-((x - 160) / 26.0) ** 2),
               12, rp('smoke:0', 'smoke:1', 'smoke:2', 'smoke:3', 'roof_red:1', 'roof_red:2', 'dusk:4'),
               rmin=6, rmax=11, down=0.55, gain=0.25)
    embers(cv, 90, 21, (0, 20, 320, 130), wind=0.3)
    return cv


@scene('序章·尾声：战后的王座厅（破碎的窗、晨光、余烬）')
def bg_throne_dawn():
    cv, carpet = throne_room('dawn')
    fallen_banner(cv, [(84, 98), (104, 101), (126, 106), (142, 114)], 5,
                  rp('INK', 'cloth_navy:0', 'cloth_navy:1', 'cloth_navy:2'), 'gold:1')
    draw_polyline(cv, [(206, 92), (232, 112)], 'INK')
    draw_polyline(cv, [(207, 92), (233, 112)], 'wood:1')
    # 地毯焦洞
    n = fbm2d(cv.w, cv.h, 9, 5, 41, 3)
    holes = carpet & (n > 0.42) & (cv.yy > 100)
    cv.fill(holes & (cv.t4 > 0.25), 'INK2')
    cv.fill(outline(holes) & carpet & (cv.t4 > 0.5), 'carpet:0')
    # 灰烬堆 + 细烟（竖直、细、飘散）
    for (x0, x1, by, sd) in [(40, 60, 128, 1), (262, 280, 128, 2), (104, 114, 108, 3), (212, 220, 104, 4)]:
        pile = ellipse_mask((x0 + x1) / 2, by, (x1 - x0) / 2, 2.5) & (cv.yy <= by)
        cv.fill(pile, 'stone:1')
        cv.fill(edge(pile, 0, -1), 'stone:3')
        flames(cv, x0 + 4, x1 - 4, by - 1, 1.5, 4, sd, density=1.2)
        rng = np.random.default_rng(sd)
        x = (x0 + x1) / 2.0
        for k in range(46):
            y = by - 4 - k
            x += math.sin(k * 0.35 + sd) * 0.6 + 0.18
            if (k // 3) % 4 != 3 and rng.random() < 0.85 - k * 0.012:
                cv.dot(x, y, 'stone:4' if k < 18 else 'stone:3')
    # 光柱中的飘尘
    rng = np.random.default_rng(3)
    for _ in range(90):
        x, y = rng.uniform(100, 260), rng.uniform(26, 124)
        if cv.light[int(y), int(x)] > 0.18:
            cv.dot(x, y, 'dawn:8' if rng.random() < 0.5 else 'dawn:7')
    embers(cv, 18, 5, (20, 60, 300, 130), cols=('fire:2', 'fire:3'), big=0.0)
    return cv


@scene('第五章·尾声：加冕礼（大厅、人群剪影、阳光、白鹿旗）')
def bg_coronation():
    cv, carpet = throne_room('coronation')
    # 立柱之间的白鹿旗
    navy = rp('cloth_navy:1', 'cloth_navy:2', 'cloth_navy:3', 'cloth_navy:4', 'cloth_sky:3')
    trim = ['gold:2', 'gold:3', 'gold:4']
    hang_banner(cv, 70, 14, 13, 44, navy, trim, DEER, 'cloth_white:4', seed=1)
    hang_banner(cv, 237, 14, 13, 44, navy, trim, DEER, 'cloth_white:4', seed=2)
    hang_banner(cv, 30, 4, 18, 64, navy, trim, DEER, 'cloth_white:4', seed=3)
    hang_banner(cv, 272, 4, 18, 64, navy, trim, DEER, 'cloth_white:4', seed=4)
    # 两侧人群剪影（由后往前一排排画：后排稍亮、前排最暗；在光柱里的头肩被勾亮）
    rng = np.random.default_rng(12)
    row_cols = ['stone:1', 'stone:0', 'INK2', 'INK']
    for row in range(4):
        crowd = np.zeros((cv.h, cv.w), bool)
        yb = 104 + row * 9
        for side in (-1, 1):
            for i in range(14):
                x = 160 + side * (26 + row * 6 + i * (7 + row * 1.5) + rng.uniform(-1.5, 1.5))
                if not (-4 <= x < 324):
                    continue
                hh = 13 + row * 2 + rng.uniform(-1, 2)
                m = Mask(cv.w, cv.h, 4)
                m.ellipse(x, yb - hh, 2.4 + row * 0.35, 2.8 + row * 0.35)
                m.poly([(x - 4 - row, yb + 30), (x - 3.5 - row * 0.5, yb - hh + 5), (x - 1.5, yb - hh + 3),
                        (x + 1.5, yb - hh + 3), (x + 3.5 + row * 0.5, yb - hh + 5), (x + 4 + row, yb + 30)])
                crowd |= m.get()
        crowd &= ~carpet | (cv.yy < 96)
        cv.fill(crowd, row_cols[row])
        r1, r2 = rim_edges(crowd, 'top')
        cv.fill(r1 & (cv.light > 0.12), 'dawn:6')
        cv.fill(r1 & (cv.light <= 0.12), 'stone:2' if row < 2 else 'stone:1')
    # 花瓣 / 光尘
    rng = np.random.default_rng(8)
    for _ in range(60):
        x, y = rng.uniform(90, 230), rng.uniform(20, 110)
        c = 'dawn:8' if cv.light[int(y), int(x)] > 0.12 else 'cloth_white:3'
        cv.dot(x, y, c)
    return cv


# ===========================================================================
# 3. 城堡地下密道（小型光线投射：拱顶走廊顺着石阶向下延伸 + 壁上火把 + 尽头一线夜色）
# ===========================================================================
@scene('序章：城堡地下密道（火把、石阶、幽暗）')
def bg_passage():
    cv = Canvas()
    f = 138.0
    vx, vy = 160.0, 58.0
    Wc, Hc, Hf = 2.3, -0.1, 2.0          # 半宽、拱脚高度（y 向下为正）、地面（摄像机沿台阶坡度看下去）
    Zend = 15.0
    dx = (cv.xx - vx) / f
    dy = (cv.yy - vy) / f
    INF = 1e9
    zbest = np.full(dx.shape, INF)
    kind = np.zeros(dx.shape, int)       # 1 左墙 2 右墙 3 拱顶 4 台阶 5 尽头
    with np.errstate(divide='ignore', invalid='ignore'):
        zl = np.where(dx < 0, -Wc / dx, INF)
        zr = np.where(dx > 0, Wc / dx, INF)
        zf = np.where(dy > 0, Hf / dy, INF)
    for kid, zz in ((1, zl), (2, zr)):
        yw = dy * zz
        ok = (yw >= Hc) & (yw <= Hf) & (zz > 0.2) & (zz < zbest)
        zbest = np.where(ok, zz, zbest)
        kind = np.where(ok, kid, kind)
    a = dx * dx + dy * dy
    b = -2 * dy * Hc
    c = Hc * Hc - Wc * Wc
    disc = b * b - 4 * a * c
    with np.errstate(invalid='ignore', divide='ignore'):
        zv = (-b + np.sqrt(np.maximum(disc, 0))) / (2 * a)
    ok = (disc > 0) & (dy * zv < Hc) & (zv > 0.2) & (zv < zbest)
    zbest = np.where(ok, zv, zbest)
    kind = np.where(ok, 3, kind)
    ok = (np.abs(dx * zf) <= Wc) & (zf < zbest)
    zbest = np.where(ok, zf, zbest)
    kind = np.where(ok, 4, kind)
    endm = zbest > Zend
    kind = np.where(endm, 5, kind)
    zbest = np.where(endm, Zend, zbest)
    Z = zbest
    X = dx * Z
    Y = dy * Z
    # 石块纹理（远处砖缝变细变淡）
    bw, bh = 0.95, 0.44
    wallm = (kind == 1) | (kind == 2)
    rowi = np.floor((Y + 5) / bh)
    zz = Z + (rowi % 2) * bw / 2
    mw = 0.12 * np.maximum(1, Z / 3.5)
    mortar = wallm & ((((Y + 5) / bh) % 1 < mw) | ((zz / bw) % 1 < mw * 0.5))
    vault = kind == 3
    ang = np.arctan2(Y - Hc, X)
    arow = np.floor(ang / 0.24)
    zz2 = Z + (arow % 2) * bw / 2
    mortar |= vault & ((((ang / 0.24) % 1) < mw * 1.1) | ((zz2 / bw) % 1 < mw * 0.5))
    # 台阶：沿坡面按 run 分段 —— [近端阴影][踏面][远端亮边]
    stairs = kind == 4
    run = 0.78
    ph = ((Z - 0.4) / run) % 1
    st_shadow = stairs & (ph < 0.22)
    st_nose = stairs & (ph > 0.9)
    # 火把光
    torches = [(-Wc + 0.08, -0.35, 2.7), (Wc - 0.08, -0.35, 6.2)]
    Lf = np.zeros(dx.shape)
    for (tx, ty, tz) in torches:
        d2 = (X - tx) ** 2 + (Y - ty) ** 2 + (Z - tz) ** 2
        Lf += 1.0 / (1 + d2 * 2.2)
    depth_dark = np.clip((Z - 1.5) / 9.0, 0, 1)
    tt = 0.17 + 0.7 * np.clip(Lf, 0, 1) ** 0.8 - 0.2 * depth_dark
    tt = tt - 0.1 * mortar - 0.12 * st_shadow + 0.1 * st_nose
    ramp_s = rp('INK', 'INK2', 'stone:0', 'stone:1', 'rock:1', 'leather:2', 'leather:3', 'leather:4')
    solid = (kind > 0) & (kind < 5)
    cv.ramp(solid, np.clip(tt, 0, 1), ramp_s, soft=0.5)
    # 尽头：出口的一线夜色（拱形小门洞）
    ex = (np.abs(X) < 1.0) & (Y > -0.4) & (Y < Hf) | ((X ** 2 + (Y + 0.4) ** 2) < 1.0)
    endwall = (kind == 5)
    cv.fill(endwall, 'INK')
    door = endwall & ex
    cv.ramp(door, 0.25 + 0.5 * np.clip(vgrad(cv, 44, 72), 0, 1),
            rp('night:1', 'night:2', 'night:3', 'night:4'), soft=0.6, gain=0)
    cv.fill(outline(door) & endwall, 'INK2')
    ys, xs = np.nonzero(door)
    if len(xs):
        cv.dot(xs.min() + 2, ys.min() + 3, 'night:7')
        cv.dot(xs.max() - 2, ys.min() + 6, 'night:6')
    # 近处台阶亮边
    cv.fill(st_nose & (Lf > 0.35) & (cv.t4 > 0.35), 'leather:4')
    # 火把（屏幕位置）
    for (tx, ty, tz) in torches:
        sx = vx + f * tx / tz
        sy = vy + f * ty / tz
        sc = 2.7 / tz
        sx, sy = int(round(sx)), int(round(sy))
        side = -1 if tx < 0 else 1
        L = max(4, int(10 * sc))
        for k_ in range(L):
            cv.dot(sx - side * (k_ // 4), sy + k_, 'wood:1' if k_ < L - 3 else 'iron:1')
            cv.dot(sx - side * (k_ // 4) + 1, sy + k_, 'wood:0' if k_ < L - 3 else 'INK')
        cv.fill(rect_mask(sx - side * (L // 4) - 1, sy + L - 2, sx - side * (L // 4) + 2, sy + L - 1), 'iron:2')
        cv.fill(rect_mask(sx - 1, sy, sx + 2, sy + 1), 'iron:1')
        flames(cv, sx - 2.5 * sc, sx + 3.5 * sc, sy + 1, 6 * sc, 12 * sc, int(tz * 10), density=3)
    # 墙上的铁环与锁链
    for (x, y0, y1) in [(34, 28, 52), (287, 40, 58)]:
        for y in range(y0, y1):
            cv.dot(x + (y % 2), y, 'iron:2' if y % 3 else 'iron:3')
    embers(cv, 16, 7, (40, 10, 280, 110), big=0.0)
    return cv


# ===========================================================================
# 户外共用：前景大树、民居、礼拜堂、烟柱
# ===========================================================================
def half_timber(cv, wallm, x0, x1, top, base, beam, seed):
    """木构架：边柱、中梁、斜撑。"""
    w = x1 - x0
    mid = (top + base) // 2
    lines = np.zeros_like(wallm)
    lines |= (cv.xx == x0) | (cv.xx == x1)
    lines |= (cv.yy == top) | (cv.yy == mid)
    for cx in range(x0 + 9, x1 - 4, 10):
        lines |= (cv.xx == cx)
    for cx in range(x0, x1 - 4, 10):
        seg = (cv.xx >= cx) & (cv.xx < cx + 9) & (cv.yy > mid) & (cv.yy < base)
        lines |= seg & (np.abs((cv.xx - cx) - (cv.yy - mid) * 9.0 / max(1, base - mid)) < 0.7)
    cv.fill(wallm & lines, beam)


def draw_house(cv, x, base, w, wall_h, roof_h, kind, state, seed, wall_r, roof_r, beam='wood:1',
               sunlit=0.0, win_lit=True, t_wall=0.55, t_roof=0.5):
    """民居：kind='gable' 正面山墙 / 'side' 侧面长屋；state='normal'/'burning'/'ruined'。
    返回 dict(wall, roof, x0, x1, top, ridge)。"""
    rng = np.random.default_rng(seed)
    mw, mr = Mask(cv.w, cv.h, 4), Mask(cv.w, cv.h, 4)
    if kind == 'gable':
        x0, x1, top, ridge = house(mw, mr, x, base, w, wall_h, roof_h, over=2)
    else:
        x0, x1, top, ridge = side_house(mw, mr, x, base, w, wall_h, roof_h, over=2, slope=0.35)
    wallm, roofm = mw.get(), mr.get()
    if state == 'ruined':
        jag = top + 1 + np.abs(fbm1d(cv.w, 4, seed, 2)) * wall_h * 0.9
        if kind == 'gable':
            # 山墙残留一个尖角
            peak = (x0 + x1) / 2 + rng.uniform(-6, 6)
            jag = np.minimum(jag, top - roof_h * 0.6 + np.abs(np.arange(cv.w) - peak) * 1.3)
        wallm &= cv.yy >= jag[None, :].repeat(cv.h, 0)
        roofm = np.zeros_like(roofm)
    u = np.clip((cv.xx - x0) / max(1.0, w), 0, 1)
    cv.fill(outline(wallm | roofm) & (cv.yy < base), 'INK')
    cv.ramp(wallm, t_wall - 0.22 * u + sunlit * (1 - u), wall_r, soft=0.5)
    if state != 'ruined':
        half_timber(cv, wallm, int(x0), int(x1), int(top), int(base), beam, seed)
    else:
        cv.fill(wallm & (cv.xx == int(x0) + 3), beam)
    # 门窗
    dx = int(x0 + w * (0.3 if kind == 'gable' else 0.2))
    door = rect_mask(dx, base - 7, dx + 3, base)
    cv.fill(door & wallm, 'INK')
    wins = [(int(x0 + w * 0.62), int(top + wall_h * 0.3)), (int(x0 + w * 0.8), int(top + wall_h * 0.3))] if kind == 'side' \
        else [(int(x0 + w * 0.62), int(top + wall_h * 0.35))]
    for (wx, wy) in wins:
        wm_ = rect_mask(wx, wy, wx + 2, wy + 2) & wallm
        if state == 'burning':
            cv.fill(wm_, 'fire:3')
            cv.fill(wm_ & (cv.yy == wy), 'fire:4')
        elif state == 'ruined':
            cv.fill(wm_, 'INK')
        else:
            cv.fill(wm_, 'fire:2' if win_lit else 'INK2')
            cv.fill(wm_ & (cv.yy == wy), 'fire:3' if win_lit else 'INK2')
    if roofm.any():
        ur = np.clip((cv.xx - (x0 - 2)) / max(1.0, w + 4), 0, 1)
        if kind == 'gable':
            sh = np.where(ur < 0.5, 0.1, -0.14)
        else:
            sh = -0.2 * np.clip(vgrad(cv, ridge, top), 0, 1) + 0.08
        cv.ramp(roofm, t_roof + sh + sunlit * 0.5 * (ur < 0.5), roof_r, soft=0.5)
        # 屋檐暗线 / 茅草纹
        cv.fill(edge(roofm, 0, 1), roof_r[0])
        n = fbm2d(cv.w, cv.h, 2, 5, seed + 3, 2)
        cv.fill(roofm & (n > 0.35) & ~edge(roofm, 0, 1), roof_r[1])
    return {'wall': wallm, 'roof': roofm, 'x0': x0, 'x1': x1, 'top': top, 'ridge': ridge}


def chapel(cv, cx, base, wall_r, roof_r, t=0.55, sunlit=0.0, win='fire:2', win2='fire:3', rim_col=None):
    """石砌礼拜堂：侧面中殿 + 钟楼（尖顶、钟洞里的钟、金色顶饰）+ 圆窗。返回整体遮罩。"""
    mw, mr = Mask(cv.w, cv.h, 4), Mask(cv.w, cv.h, 4)
    side_house(mw, mr, cx - 30, base, 60, 22, 12, over=2, slope=0.4)
    nave, nroof = mw.get(), mr.get()
    tw = Mask(cv.w, cv.h, 4)
    tw.rect(cx - 8, base - 70, cx + 7, base)
    tower_m = tw.get()
    tr = Mask(cv.w, cv.h, 4)
    tr.poly([(cx - 10.5, base - 70), (cx - 0.5, base - 92), (cx + 9.5, base - 70)])
    troof = tr.get()
    u = np.clip((cv.xx - (cx - 30)) / 60.0, 0, 1)
    allm = nave | nroof | tower_m | troof
    cv.fill(outline(allm) & (cv.yy < base), 'INK')
    cv.ramp(nave, t - 0.2 * u + sunlit * (1 - u), wall_r, soft=0.5)
    cv.ramp(nroof, t - 0.05 - 0.2 * np.clip(vgrad(cv, base - 34, base - 22), 0, 1), roof_r, soft=0.5)
    cv.fill(edge(nroof, 0, 1), roof_r[0])
    ut = np.clip((cv.xx - (cx - 8)) / 15.0, 0, 1)
    cv.ramp(tower_m, t + 0.05 - 0.3 * ut + sunlit * (ut < 0.4), wall_r, soft=0.5)
    urf = np.clip((cv.xx - (cx - 10)) / 20.0, 0, 1)
    cv.ramp(troof, t + np.where(urf < 0.5, 0.1, -0.14) + sunlit * 0.4 * (urf < 0.5), roof_r, soft=0.5)
    # 石缝
    cv.fill(tower_m & ((cv.yy - base) % 6 == 0) & (cv.t4 > 0.5), wall_r[1])
    # 钟洞 + 钟
    bell = rect_mask(cx - 4, base - 64, cx + 3, base - 54) | rect_mask(cx - 3, base - 65, cx + 2, base - 65)
    cv.fill(bell, 'INK')
    cv.fill(rect_mask(cx - 2, base - 61, cx + 1, base - 57), 'gold:2')
    cv.fill(rect_mask(cx - 2, base - 61, cx - 2, base - 58), 'gold:3')
    cv.fill(rect_mask(cx - 3, base - 57, cx + 2, base - 57), 'gold:1')
    # 顶饰
    cv.dot(cx - 1, base - 93, 'gold:3')
    cv.dot(cx - 1, base - 94, 'gold:4')
    cv.dot(cx - 1, base - 95, 'gold:3')
    cv.dot(cx - 2, base - 94, 'gold:2')
    cv.dot(cx, base - 94, 'gold:2')
    # 圆窗 + 尖拱窗
    rw = ellipse_mask(cx - 0.5, base - 42, 3.2, 3.2)
    cv.fill(dilate(rw, 1) & ~rw, wall_r[1])
    cv.fill(rw, win)
    cv.dot(cx - 1, base - 43, win2)
    for wx in (cx - 22, cx - 16, cx + 13, cx + 19):
        m = rect_mask(wx, base - 16, wx + 2, base - 8) & ~rect_mask(wx, base - 16, wx, base - 16) & ~rect_mask(wx + 2, base - 16, wx + 2, base - 16)
        cv.fill(m, win)
        cv.fill(m & (cv.yy <= base - 14), win2)
    door = rect_mask(cx - 3, base - 11, cx + 2, base) & ~rect_mask(cx - 3, base - 11, cx - 3, base - 11) & ~rect_mask(cx + 2, base - 11, cx + 2, base - 11)
    cv.fill(door, 'wood:1')
    cv.fill(door & (cv.xx == cx - 1), 'INK')
    if rim_col:
        r1, r2 = rim_edges(allm, 'ul')
        cv.fill(r1 | r2, rim_col)
    return allm


def smoke_plumes(cv, plumes, ramp, lit_from=None, seed=0, thr=0.45, gain=0.0, t0=0.12, lit_amt=0.55):
    """若干股烟柱合成一片：plumes = [(sx, sy, 高, 底宽, 顶宽, 倾斜)]。靠近火源的下部更亮。"""
    dens = np.zeros((cv.h, cv.w))
    lit = np.zeros((cv.h, cv.w))
    for i, (sx, sy, hgt, w0, w1, lean) in enumerate(plumes):
        d = smoke_field(cv, sx, sy, hgt, w0, w1, lean, seed + i * 17, px=14, py=11, rough=0.45)
        dens = np.maximum(dens, d)
        lit = np.maximum(lit, np.clip(1 - (sy - cv.yy) / (hgt * 0.45), 0, 1) * (d > thr))
    m = dens > thr
    t = t0 + 0.12 * np.clip(dens - thr, 0, 1) + lit_amt * lit ** 1.4
    cv.ramp(m, t, ramp, soft=0.6, gain=gain)
    # 烟团上缘的暗线让体积更清楚
    cv.fill(edge(m, 0, -1) & (cv.t4 > 0.45), ramp[0])
    return m


# ===========================================================================
# 4. 夜晚林间，远处山丘上的王城在燃烧
# ===========================================================================
def canopy(cv, clusters, seed, rough=True):
    """树冠：若干椭圆叶团拼成，边缘用噪声打散成叶簇感。"""
    cm = Mask(cv.w, cv.h, 4)
    for (cx, cy, rx, ry) in clusters:
        cm.ellipse(cx, cy, rx, ry)
    can = cm.get()
    if rough:
        n = fbm2d(cv.w, cv.h, 2.5, 2.5, seed, 2)
        band = dilate(can, 2) & ~erode(can, 2)
        can = (can & ~(band & (n < -0.22))) | (band & (n > 0.28))
        can = clean(can)
    return can


def forest_tree(cv, x, base, w, lean, seed, side, clusters, body='INK', rim_col=None, bark='INK2'):
    """前景大树：粗树干（带树皮纹）+ 伸向画面中央的枝杈 + 顶部树冠。side=1 表示树在左边、光从右来。"""
    rng = np.random.default_rng(seed)
    mm = Mask(cv.w, cv.h, 4)
    pts_l, pts_r = [], []
    for i in range(25):
        s = i / 24.0
        y = base - s * (base + 30)
        cx = x + lean * s ** 1.4 * 40
        hw = w / 2.0 * (1 - 0.4 * s) + (5 if s < 0.05 else 0) * (1 - s / 0.05)
        pts_l.append((cx - hw, y))
        pts_r.append((cx + hw, y))
    mm.poly(pts_l + pts_r[::-1])
    for (s, L, ang) in [(0.55, 38, -0.5), (0.72, 30, -0.9), (0.4, 22, -0.25)]:
        y0 = base - s * (base + 30)
        x0 = x + lean * s ** 1.4 * 40
        x1 = x0 + side * L * math.cos(ang)
        y1 = y0 + L * math.sin(ang)
        th = w * 0.16 + 1
        mm.poly([(x0, y0 - th), (x1, y1), (x0, y0 + th)])
    trunk = mm.get()
    can = canopy(cv, clusters, seed + 1)
    m = trunk | can
    cv.fill(m, body)
    # 树皮纹：朝光一侧的竖向细纹
    n = fbm2d(cv.w, cv.h, 1.5, 9, seed + 2, 2)
    cv.fill(trunk & (n > 0.25) & ~can, bark)
    if rim_col:
        r = (edge(trunk, side, 0) | edge(can, side, 0) | edge(can, 0, 1)) & (cv.yy > 2)
        cv.fill(r & (cv.t4 > 0.2), rim_col)
    return m


@scene('序章：夜晚林间，远处山丘上的王城在燃烧')
def bg_forest_night():
    cv = Canvas()
    cv.light = vignette(cv, 0.14)
    glow = radial(cv, 160, 100, 230, aspect=2.2)
    sky = rp('night:0', 'night:1', 'night:2', 'night:3', 'dusk:2', 'dusk:3', 'dusk:4', 'dusk:5', 'dusk:6')
    t = 0.3 * np.clip(vgrad(cv, 0, 100), 0, 1) ** 1.3 + 0.72 * glow ** 2.2
    cv.ramp(None, t, sky, soft=0.7)
    stars(cv, (t < 0.42), 120, 5, ymax=110, bias=1.3)
    # 城市升起的烟柱（被火光从下方映红）
    smoke_plumes(cv, [(164, 76, 96, 10, 58, 0.75), (140, 80, 70, 6, 30, 0.9), (186, 80, 60, 6, 26, 1.1)],
                 rp('smoke:0', 'smoke:1', 'smoke:2', 'smoke:3', 'roof_red:1', 'dusk:4', 'dusk:5'), seed=7)
    # 远山
    far = height_mask(ridge_line(cv.w, 100, 9, 60, 21, 3))
    cv.ramp(far, 0.2 + 0.45 * glow ** 1.5, rp('INK', 'night:1', 'dusk:1', 'dusk:2', 'dusk:3'), soft=0.5)
    # 王城所在的山丘
    xs = np.arange(cv.w)
    hill_top = 100 - 17 * np.exp(-((xs - 160) / 48.0) ** 2) + fbm1d(cv.w, 8, 3, 2) * 1.5
    hill = height_mask(hill_top)
    cv.ramp(hill, 0.2 + 0.25 * glow, rp('INK', 'INK2', 'dusk:1', 'dusk:2'), soft=0.5)
    cv.fill(edge(hill, 0, -1) & (glow > 0.55), 'dusk:4')
    # 燃烧的白鹿城
    cs = royal_castle(160, 86, s=0.4)
    draw_castle(cv, cs, body=rp('INK', 'INK2', 'dusk:1', 'dusk:2'), roof=rp('INK', 'INK2', 'dusk:1', 'dusk:2'),
                t_body=0.25, t_roof=0.3, rim='fire:1', rim2=None, mode='top')
    lit_windows(cv, cs['windows'], cs['mask'], cols=('fire:2', 'fire:3'), seed=9, frac=0.95)
    for (fx, fy, fw, fh, sd) in [(152, 60, 5, 7, 1), (170, 64, 4, 6, 2), (142, 78, 6, 5, 3), (180, 78, 7, 6, 4), (130, 76, 3, 4, 5), (160, 44, 3, 5, 6)]:
        flames(cv, fx - fw / 2, fx + fw / 2, fy, fh * 0.5, fh, sd, density=2.0)
    flames(cv, 118, 204, 88, 3, 7, 8, density=1.4)
    # 中景针叶林（树梢有火光轮廓）
    fl = height_mask(conifer_line(cv.w, 124, 14, 26, 8, 31))
    cv.fill(fl, 'INK2')
    cv.fill(edge(fl, 0, -1) & (glow > 0.45), 'dusk:3')
    fl2 = height_mask(conifer_line(cv.w, 134, 10, 20, 7, 32))
    cv.fill(fl2, 'INK')
    cv.fill(edge(fl2, 0, -1) & (glow > 0.6) & (cv.t4 > 0.5), 'dusk:2')
    # 前景大树框住画面（树冠在两个上角，树干受远处火光勾边）
    forest_tree(cv, 16, 184, 26, 0.15, 41, 1,
                [(8, 2, 36, 24), (46, 12, 28, 16), (82, 4, 22, 12), (24, 30, 20, 12), (104, -4, 18, 10), (60, 26, 12, 7)], rim_col='dusk:2')
    forest_tree(cv, 304, 184, 28, -0.2, 42, -1,
                [(312, 2, 34, 24), (274, 14, 28, 16), (240, 4, 22, 12), (296, 32, 20, 12), (216, -4, 16, 10), (258, 28, 12, 7)], rim_col='dusk:2')
    forest_tree(cv, 66, 190, 10, 0.08, 43, 1, [(60, -30, 1, 1)], rim_col='dusk:2')
    ground = height_mask(150 + fbm1d(cv.w, 20, 4, 3) * 4)
    cv.fill(ground, 'INK')
    # 远方飘来的火星
    embers(cv, 16, 44, (110, 40, 220, 90), cols=('fire:2', 'fire:3'), big=0.0)
    return cv


# ===========================================================================
# 5 / 6. 石溪村：燃烧中 / 劫后（同一布局）
# ===========================================================================
VILLAGE = [
    # x, base, w, 墙高, 屋顶高, 类型
    (2, 114, 36, 17, 15, 'gable'),
    (44, 111, 42, 14, 11, 'side'),
    (92, 112, 26, 14, 12, 'gable'),
    (202, 112, 28, 14, 12, 'gable'),
    (236, 111, 44, 15, 11, 'side'),
    (286, 114, 34, 17, 15, 'gable'),
]


def village(mode):
    cv = Canvas()
    burning = mode == 'burning'
    cv.light = vignette(cv, 0.14)
    if burning:
        sky = rp('dusk:1', 'dusk:2', 'dusk:3', 'dusk:4', 'dusk:5', 'dusk:6', 'dusk:7')
        t = np.clip(vgrad(cv, -20, 104), 0, 1) ** 1.1
        cv.ramp(None, t, sky, soft=0.55)
    else:
        sun = (54, 92)
        sky = rp('dusk:0', 'dusk:1', 'dusk:2', 'dusk:3', 'dusk:4', 'dusk:5', 'dusk:6', 'dusk:7', 'dusk:8')
        t = 0.62 * np.clip(vgrad(cv, -10, 104), 0, 1) ** 1.2 + 0.4 * radial(cv, sun[0], sun[1], 150, 1.6) ** 1.5
        cv.ramp(None, t, sky, soft=0.55)
        # 低垂的夕阳
        sd = ellipse_mask(sun[0], sun[1], 11, 11)
        cv.fill(sd, 'dusk:8')
        cv.fill(sd & ellipse_mask(sun[0] - 2, sun[1] - 2, 7, 7), 'dawn:8')
        # 横向霞云（下缘被夕阳照亮）
        for (x0, x1, cy, th, sdd) in [(120, 340, 40, 7, 3), (170, 330, 60, 5, 4), (-20, 110, 22, 6, 5), (70, 160, 72, 3, 6), (196, 300, 18, 4, 7)]:
            streak_cloud(cv, x0, x1, cy, th, sdd, rp('dusk:2', 'dusk:3', 'dusk:4', 'dusk:6', 'dusk:7'))
    # 远山
    far = height_mask(ridge_line(cv.w, 96, 10, 70, 11, 3))
    cv.ramp(far, 0.45, rp('dusk:1', 'dusk:2', 'dusk:3', 'dusk:4'), soft=0.5)
    near_h = height_mask(ridge_line(cv.w, 104, 5, 40, 12, 3))
    cv.ramp(near_h, 0.4, rp('INK', 'dusk:0', 'dusk:1', 'dusk:2'), soft=0.5)
    # 树
    trees = np.zeros((cv.h, cv.w), bool)
    for (tx, th, sd) in [(40, 26, 1), (86, 20, 2), (124, 22, 3), (196, 24, 4), (232, 18, 5), (280, 28, 6)]:
        trees = round_tree(trees, tx, 112, th, sd)
    if burning:
        cv.fill(trees, 'INK2')
        cv.fill(edge(trees, 0, -1), 'dusk:4')
    else:
        cv.fill(trees, 'INK2')
        cv.fill(edge(trees, -1, 0) | edge(trees, 0, -1) & (cv.xx < 160), 'dusk:4')
    # 烟柱（燃烧：浓烟直冲；劫后：几缕余烟）
    if burning:
        plumes = [(20, 104, 110, 8, 44, 0.55), (64, 102, 120, 9, 50, 0.6), (104, 104, 90, 6, 34, 0.6),
                  (214, 104, 110, 7, 44, 0.6), (256, 102, 124, 10, 54, 0.55), (302, 106, 90, 7, 36, 0.5)]
        smoke_plumes(cv, plumes, rp('smoke:0', 'smoke:1', 'smoke:2', 'smoke:3', 'roof_red:1', 'dusk:4', 'dusk:6'), seed=3)
    else:
        rng = np.random.default_rng(4)
        for (sx, sy) in [(22, 104), (66, 102), (216, 104), (258, 102), (300, 106)]:
            x = float(sx)
            for k in range(60):
                y = sy - k
                x += math.sin(k * 0.22 + sx) * 0.5 + 0.28
                if rng.random() < 0.8 - k * 0.011:
                    c = 'smoke:4' if k < 25 else 'dusk:3'
                    cv.dot(x, y, c)
                    if k > 12 and rng.random() < 0.5:
                        cv.dot(x + 1, y, c)
    # 礼拜堂（两种状态都完好）
    if burning:
        chapel(cv, 160, 112, rp('INK', 'stone:1', 'stone:2', 'roof_red:2', 'dusk:5', 'dusk:6'),
               rp('INK', 'roof_blue:0', 'roof_blue:1', 'roof_blue:2', 'dusk:4'), t=0.5, rim_col='dusk:6')
    else:
        chapel(cv, 160, 112, rp('INK', 'stone:1', 'stone:2', 'stone:3', 'dusk:6', 'dusk:7'),
               rp('INK', 'roof_blue:0', 'roof_blue:1', 'roof_blue:2', 'dusk:5'), t=0.42, sunlit=0.28,
               win='fire:2', win2='fire:3', rim_col='dusk:7')
    # 民居
    if burning:
        for (x, base, w, wh, rh, kind) in VILLAGE:
            cv.light += radial(cv, x + w / 2.0, base - wh - rh * 0.5, 44, 1.2) ** 1.5 * 0.22
    for i, (x, base, w, wh, rh, kind) in enumerate(VILLAGE):
        if burning:
            h = draw_house(cv, x, base, w, wh, rh, kind, 'normal', 10 + i,
                           rp('INK', 'leather:1', 'leather:2', 'leather:3', 'dusk:6', 'dusk:7'),
                           rp('INK', 'wood:0', 'wood:1', 'wood:2', 'dusk:5', 'dusk:6'), beam='wood:0', t_wall=0.42, t_roof=0.4)
            # 屋顶起火：只烧屋顶的一段，屋顶轮廓仍看得出
            x0, x1, top, ridge = h['x0'], h['x1'], h['top'], h['ridge']
            rng = np.random.default_rng(60 + i)
            xc, hw = (x0 + x1) / 2.0, (x1 - x0) / 2.0 + 2
            if kind == 'gable':
                base_y = ridge + (top - ridge) * 0.5
                off = rng.uniform(-0.2, 0.2) * hw
                a, b = xc - hw * 0.62 + off, xc + hw * 0.62 + off
            else:
                base_y = ridge + 1.5
                inset = (top - ridge) * 0.4
                span = (x1 - x0) - 2 * inset
                a = x0 + inset + rng.uniform(0.0, 0.35) * span
                b = a + rng.uniform(0.55, 0.8) * span
            scorch = ellipse_mask((a + b) / 2.0, base_y + 2, (b - a) / 2.0 + 3, (top - ridge) * 0.55 + 1) & h['roof']
            cv.fill(scorch & (cv.t4 > 0.35), 'INK2')
            cv.fill(scorch & (cv.t4 <= 0.35), 'roof_red:1')
            flames(cv, a, b, base_y, 12, 24 + (top - ridge) * 1.2, 20 + i, density=1.5)
            # 墙根也有火苗窜出
            if i % 2 == 0:
                flames(cv, x0 + 2, x0 + w * 0.4, base, 4, 9, 40 + i, density=1.5)
        else:
            draw_house(cv, x, base, w, wh, rh, kind, 'ruined', 10 + i,
                       rp('INK', 'smoke:1', 'smoke:2', 'smoke:3', 'rock:2', 'dusk:6'),
                       rp('INK', 'wood:0', 'wood:1', 'wood:2'), beam='INK', sunlit=0.22, t_wall=0.38)
            # 烧焦的椽子
            rng = np.random.default_rng(30 + i)
            for k in range(3):
                bx = x + rng.uniform(4, w - 4)
                L = rng.uniform(8, 14)
                a = rng.uniform(-0.9, 0.9)
                draw_polyline(cv, [(bx, base - wh + 2), (bx + math.sin(a) * L, base - wh + 2 - math.cos(a) * L)], 'INK')
    # 地面、篱笆、道路
    gr = rect_mask(0, 114, 319, 179)
    if burning:
        cv.ramp(gr, 0.5 - 0.35 * np.clip(vgrad(cv, 114, 150), 0, 1), rp('INK', 'INK2', 'leather:1', 'leather:2', 'roof_red:2', 'dusk:5'), soft=0.5)
    else:
        cv.ramp(gr, 0.45 - 0.35 * np.clip(vgrad(cv, 114, 150), 0, 1), rp('INK', 'INK2', 'smoke:2', 'smoke:3', 'dusk:3', 'dusk:5'), soft=0.5)
    road = poly_mask([(148, 114), (172, 114), (214, 180), (106, 180)])
    cv.ramp(road, 0.58 - 0.3 * np.clip(vgrad(cv, 114, 160), 0, 1),
            rp('INK', 'INK2', 'leather:1', 'leather:2', 'earth:2', 'dusk:6') if burning else rp('INK', 'INK2', 'smoke:3', 'rock:2', 'dusk:5', 'dusk:6'), soft=0.5)
    # 篱笆
    fence = np.zeros((cv.h, cv.w), bool)
    for fx in range(0, 320, 7):
        if 100 < fx < 218:
            continue
        broken = (not burning) and (fx // 7) % 5 == 2
        top = 118 + (4 if broken else 0)
        fence |= rect_mask(fx, top, fx + 1, 128)
    rail_gap = ((cv.xx // 7) % 5 == 2) if not burning else np.zeros_like(fence)
    fence |= (rect_mask(0, 121, 100, 121) | rect_mask(220, 121, 319, 121)) & ~rail_gap
    fence |= rect_mask(0, 125, 100, 125) | rect_mask(220, 125, 319, 125)
    cv.fill(fence, 'INK')
    cv.fill(edge(fence, 0, -1), 'dusk:5' if burning else 'dusk:4')
    if burning:
        embers(cv, 110, 13, (0, 20, 320, 120), wind=0.4)
    else:
        # 盘旋的乌鸦
        for (bx, by, sz, fl) in [(210, 30, 1, 0), (226, 38, 1, 1), (244, 28, 1, 0), (120, 46, 1, 1)]:
            bird(cv, bx, by, 'INK', sz, fl)
    return cv


@scene('第一章：燃烧的边境村（黄昏、浓烟、屋顶着火）')
def bg_village_burning():
    return village('burning')


@scene('第一章·战后：劫后的村庄（黄昏、余烟、废墟、礼拜堂尚存）')
def bg_village_after():
    return village('after')


# ===========================================================================
# 7. 王都广场（瓦尔德公开处决）
# ===========================================================================
def townhouse(cv, x, base, w, h, seed, wall_r, roof_r, face=1, lit_frac=0.15, win_col='INK', stepped=False):
    """城市联排高屋：立面 + 山墙（普通三角 / 阶梯山墙）+ 成排窗户。face=1 左侧受光。"""
    rng = np.random.default_rng(seed)
    x0, x1 = int(x), int(x + w - 1)
    top = int(base - h)
    fac = rect_mask(x0, top, x1, base)
    gh = int(w * 0.55)
    mg = Mask(cv.w, cv.h, 4)
    cxg = (x0 + x1) / 2.0
    if stepped:
        steps = 3
        for k in range(steps):
            inset = (w / 2.0) * k / steps
            mg.rect(int(x0 + inset), int(top - gh * (k + 1) / steps), int(x1 - inset), top)
    else:
        mg.poly([(x0 - 1, top + 1), (cxg, top - gh), (x1 + 1, top + 1)])
    gable = mg.get()
    allm = fac | gable
    cv.fill(outline(allm), 'INK')
    u = np.clip((cv.xx - x0) / max(1.0, w), 0, 1)
    cv.ramp(fac | (gable if stepped else np.zeros_like(gable)), 0.5 - 0.2 * u * face, wall_r, soft=0.5)
    if not stepped:
        cv.ramp(gable, 0.5 + np.where(cv.xx < cxg, 0.1, -0.14), roof_r, soft=0.5)
        cv.fill(edge(gable, 0, 1), roof_r[0])
    # 楼层线 + 窗
    for fy in range(top + 6, base - 6, 9):
        cv.fill(rect_mask(x0, fy + 5, x1, fy + 5) & fac, wall_r[1])
        for wx in range(x0 + 3, x1 - 2, 6):
            lit = rng.random() < 0.12
            cv.fill(rect_mask(wx, fy, wx + 1, fy + 3), 'fire:2' if lit else win_col)
            cv.fill(rect_mask(wx, fy + 4, wx + 2, fy + 4), wall_r[-1])
    # 门
    dx = int(cxg - 2)
    cv.fill(rect_mask(dx, base - 7, dx + 3, base), 'INK')
    cv.fill(edge(allm, -face, 0) & (cv.yy > top - gh), wall_r[-1])
    return allm


@scene('第二章·幕间：王都广场（黑鹰旗、处刑台、阴沉天空）')
def bg_capital_square():
    cv = Canvas()
    cv.light = vignette(cv, 0.14)
    sky = rp('overcast:0', 'overcast:1', 'overcast:2', 'overcast:3', 'overcast:4', 'overcast:5')
    cv.ramp(None, np.clip(vgrad(cv, -10, 90), 0, 1) ** 0.9, sky, soft=0.55)
    # 低垂的乌云（团状，底部暗）
    rng = np.random.default_rng(2)
    items = [(rng.uniform(-10, 330), rng.uniform(2, 30), rng.uniform(8, 15)) for _ in range(26)]
    items.sort(key=lambda it: it[1])
    puffs(cv, items, rp('overcast:1', 'overcast:2', 'overcast:3', 'overcast:4', 'overcast:5'), up=0.3, down=-0.1, gain=0.4)
    # 后方大教堂：中央高塔 + 两侧小尖塔 + 山墙
    back = Mask(cv.w, cv.h, 4)
    back.rect(108, 44, 212, 104)
    back.poly([(104, 45), (160, 22), (216, 45)])
    back.rect(146, 4, 174, 60)
    back.poly([(144, 5), (160, -16), (176, 5)])
    for sx in (112, 200):
        back.rect(sx, 26, sx + 8, 60)
        back.poly([(sx - 1, 27), (sx + 4, 12), (sx + 9, 27)])
    bm = back.get()
    u = np.clip((cv.xx - 104) / 112.0, 0, 1)
    bh_, bv_ = brick_lines(cv.xx, cv.yy, 10, 5)
    cv.ramp(bm, 0.54 - 0.2 * u - 0.07 * (bh_ | bv_), rp('INK', 'stone:0', 'stone:1', 'stone:2', 'stone:3'), soft=0.5)
    r1, r2 = rim_edges(bm)
    cv.fill(r1 | r2, 'overcast:5')
    for (wx, wy, ww, wh) in [(114, 34, 3, 7), (202, 34, 3, 7)]:
        cv.fill(rect_mask(wx, wy, wx + ww, wy + wh), 'INK')
    rose = ellipse_mask(160, 64, 8, 8)
    cv.fill(rose, 'INK')
    cv.fill(rose & ((cv.xx == 160) | (cv.yy == 64) | (np.abs(np.sqrt((cv.xx - 160) ** 2 + (cv.yy - 64) ** 2) - 5) < 0.6)), 'stone:1')
    black = rp('cloth_black:0', 'cloth_black:1', 'cloth_black:2', 'cloth_black:3', 'cloth_black:4')
    trim = ['INK', 'cloth_crimson:2', 'cloth_crimson:3']
    # 高塔上的巨幅黑鹰旗 + 立面两幅
    hang_banner(cv, 151, 14, 18, 34, black, trim, EAGLE, 'cloth_crimson:3', seed=1)
    for bx in (122, 185):
        hang_banner(cv, bx, 48, 13, 30, black, trim, EAGLE, 'cloth_crimson:3', seed=bx)
    # 两侧联排高屋（近大远小）
    wall_r = rp('INK', 'stone:1', 'stone:2', 'rock:2', 'rock:3')
    roof_r = rp('INK', 'roof_blue:0', 'roof_blue:1', 'overcast:3', 'overcast:4')
    for (x, base, w, h, sd, st) in [(86, 102, 16, 34, 1, False), (66, 104, 20, 40, 2, True), (40, 108, 26, 50, 3, False), (4, 114, 36, 62, 4, True)]:
        townhouse(cv, x, base, w, h, sd, wall_r, roof_r, face=1, stepped=st)
    for (x, base, w, h, sd, st) in [(218, 102, 16, 34, 5, True), (234, 104, 20, 40, 6, False), (254, 108, 26, 50, 7, True), (280, 114, 36, 62, 8, False)]:
        townhouse(cv, x, base, w, h, sd, wall_r, roof_r, face=-1, stepped=st)
    for (bx, by) in [(18, 70), (291, 70), (48, 72), (262, 72)]:
        hang_banner(cv, bx, by, 9, 22, black, trim, None, None, seed=bx)
        stamp(cv, ['..x..', 'xxxxx', '.xxx.', '.x.x.'], bx + 2, by + 6, 'cloth_crimson:3')
    # 处刑台
    wood = rp('INK', 'wood:0', 'wood:1', 'wood:2', 'wood:3')
    plat = rect_mask(112, 92, 208, 97)
    cv.fill(outline(plat), 'INK')
    cv.ramp(plat, 0.6, wood, soft=0.5)
    cv.fill(rect_mask(112, 92, 208, 92), 'wood:3')
    legs = np.zeros_like(plat)
    for lx in range(114, 208, 12):
        legs |= rect_mask(lx, 98, lx + 1, 112)
    legs |= rect_mask(112, 98, 208, 99)
    cv.fill(legs, 'wood:0')
    # 台前垂下的黑布
    drape = rect_mask(118, 98, 202, 104) & ~(((cv.xx - 118) % 14 > 11) & (cv.yy > 102))
    cv.ramp(drape, 0.5 - 0.3 * np.clip((cv.xx - 118) / 84.0, 0, 1), black, soft=0.5)
    stamp(cv, EAGLE, 154, 97, 'cloth_crimson:2')
    # 台阶
    for k in range(5):
        cv.fill(rect_mask(98 + k * 3, 110 - k * 4, 112, 112 - k * 4), 'wood:1' if k % 2 else 'wood:2')
    # 绞架
    for gx in (136, 182):
        cv.fill(rect_mask(gx, 56, gx + 2, 92), 'wood:1')
        cv.fill(rect_mask(gx, 56, gx, 92), 'wood:3')
        cv.fill(rect_mask(gx + 2, 56, gx + 2, 92), 'wood:0')
    cv.fill(rect_mask(130, 53, 190, 56), 'wood:1')
    cv.fill(rect_mask(130, 53, 190, 53), 'wood:3')
    cv.fill(rect_mask(130, 56, 190, 56), 'wood:0')
    draw_polyline(cv, [(139, 62), (145, 56)], 'wood:1')
    draw_polyline(cv, [(181, 62), (175, 56)], 'wood:1')
    for (nx, L) in ((152, 16), (168, 18)):
        cv.fill(rect_mask(nx, 57, nx, 57 + L), 'leather:3')
        loop = ellipse_mask(nx, 57 + L + 3, 2.2, 3) & ~ellipse_mask(nx, 57 + L + 3, 1.1, 2)
        cv.fill(loop, 'leather:3')
    # 横梁上的乌鸦 + 天上的鸟
    for (cx_, cy_) in [(140, 52), (176, 52)]:
        cv.fill(rect_mask(cx_, cy_ - 2, cx_ + 2, cy_), 'INK')
        cv.dot(cx_ + 3, cy_ - 2, 'INK')
        cv.dot(cx_ - 1, cy_ - 1, 'INK')
    for (bx, by, fl) in [(92, 22, 0), (104, 28, 1), (232, 18, 1)]:
        bird(cv, bx, by, 'INK', 1, fl)
    # 人群与卫兵长枪
    crowd = np.zeros((cv.h, cv.w), bool)
    rng = np.random.default_rng(5)
    for row in range(3):
        yb = 112 + row * 7
        x = -4 + rng.uniform(0, 5)
        while x < 324:
            m = Mask(cv.w, cv.h, 4)
            r = 2.6 + row * 0.5
            m.ellipse(x, yb - 7 - rng.uniform(0, 2), r, r * 1.1)
            m.poly([(x - r - 2, yb + 6), (x - r, yb - 4), (x + r, yb - 4), (x + r + 2, yb + 6)])
            crowd |= m.get()
            x += rng.uniform(5.5, 8) + row
    cv.fill(crowd, 'INK2')
    cv.fill(edge(crowd, 0, -1), 'overcast:3')
    for sx in (104, 122, 198, 216):
        cv.fill(rect_mask(sx, 84, sx, 112), 'iron:2')
        cv.dot(sx, 83, 'iron:4')
        cv.dot(sx, 82, 'iron:3')
    cv.fill(rect_mask(0, 128, 319, 179), 'INK')
    return cv


# ===========================================================================
# 8. 黑水河断桥
# ===========================================================================
@scene('第二章：黑水河（被炸断的石桥、北边远处木桥、阴天河雾）')
def bg_river_bridge():
    cv = Canvas()
    cv.light = vignette(cv, 0.12)
    sky = rp('overcast:2', 'overcast:3', 'overcast:4', 'overcast:5', 'overcast:6', 'mist:4')
    cv.ramp(None, np.clip(vgrad(cv, -20, 80), 0, 1), sky, soft=0.55)
    rng = np.random.default_rng(4)
    items = [(rng.uniform(-10, 330), rng.uniform(0, 24), rng.uniform(8, 14)) for _ in range(18)]
    items.sort(key=lambda it: it[1])
    puffs(cv, items, rp('overcast:2', 'overcast:3', 'overcast:4', 'overcast:5', 'overcast:6'), up=0.35, gain=0.3)
    # 远岸：雾中的丘陵与林线
    far = height_mask(ridge_line(cv.w, 70, 10, 70, 8, 3))
    cv.ramp(far, 0.55, rp('mist:1', 'mist:2', 'mist:3', 'mist:4'), soft=0.5)
    far2 = height_mask(conifer_line(cv.w, 82, 5, 11, 5, 9))
    cv.ramp(far2, 0.4, rp('mist:0', 'mist:1', 'mist:2', 'mist:3'), soft=0.5)
    # 河面（远处映着天光，近处发黑）
    river = rect_mask(0, 82, 319, 179)
    cv.ramp(river, 0.62 - 0.55 * np.clip(vgrad(cv, 82, 150), 0, 1) ** 0.8,
            rp('INK', 'overcast:0', 'mist:0', 'mist:1', 'mist:2', 'mist:3'), soft=0.5)
    # 远处（北）木桥：栈桥式，桥墩一排木桩
    # 从断口望出去，正好看见远处的木桥
    wb = rect_mask(104, 84, 222, 85)
    for px_ in range(106, 222, 9):
        wb |= rect_mask(px_, 86, px_ + 1, 92)
    for px_ in range(104, 222, 4):
        wb |= rect_mask(px_, 81, px_, 83)
    wb |= rect_mask(104, 80, 222, 80)
    cv.fill(wb, 'mist:0')
    cv.fill(rect_mask(104, 84, 222, 84), 'mist:2')
    for px_ in range(106, 222, 9):
        cv.fill(rect_mask(px_, 94, px_ + 1, 96) & (cv.t4 > 0.4), 'mist:1')
    # 桥上赶路的小小人影
    for (hx, hy) in [(150, 79), (154, 79), (170, 79)]:
        cv.fill(rect_mask(hx, hy - 3, hx, hy), 'mist:0')
        cv.dot(hx, hy - 4, 'mist:0')
    # 石桥
    stone = rp('INK', 'stone:1', 'stone:2', 'stone:3', 'stone:4', 'stone:5')
    deck_top, deck_bot, spring, water = 64, 74, 98, 114
    piers = [(-14, 10), (48, 12), (116, 12), (204, 12), (272, 12), (334, 12)]
    body = rect_mask(-1, deck_top, 320, water)
    openings = np.zeros_like(body)
    rings = np.zeros_like(body)
    joints = np.zeros_like(body)
    for (pa, wa), (pb, wb_) in zip(piers, piers[1:]):
        xa, xb = pa + wa / 2.0, pb - wb_ / 2.0
        cx, r = (xa + xb) / 2.0, (xb - xa) / 2.0
        rise = spring - (deck_bot + 4)
        k = r / float(rise)
        ell = ((cv.xx - cx) ** 2 + ((cv.yy - spring) * k) ** 2) < r * r
        op = (ell & (cv.yy <= spring)) | ((cv.xx > xa) & (cv.xx < xb) & (cv.yy > spring))
        openings |= op
        ring_o = ((cv.xx - cx) ** 2 + ((cv.yy - spring) * k) ** 2) < (r + 4) ** 2
        rings |= ring_o & ~op & (cv.yy <= spring + 1)
        ang = np.arctan2((cv.yy - spring) * k, cv.xx - cx)
        joints |= ring_o & ~op & (np.abs(((ang / np.pi * 11) % 1) - 0.5) > 0.42) & (cv.yy <= spring)
    bridge = body & ~openings
    # 中跨被炸断：两端锯齿断口
    jag_l = 128 + np.abs(fbm1d(cv.h, 2.5, 7, 2)) * 9 + np.clip(np.arange(cv.h) - 80, 0, 40) * 0.25
    jag_r = 192 - np.abs(fbm1d(cv.h, 2.5, 8, 2)) * 9 - np.clip(np.arange(cv.h) - 80, 0, 40) * 0.25
    gap = (cv.xx > jag_l[:, None]) & (cv.xx < jag_r[:, None])
    bridge &= ~gap
    rings &= bridge
    joints &= bridge
    u = np.clip(vgrad(cv, deck_top, water), 0, 1)
    bh_, bv_ = brick_lines(cv.xx, cv.yy - deck_top, 9, 5)
    cv.ramp(bridge, 0.62 - 0.3 * u - 0.08 * (bh_ | bv_), stone, soft=0.5)
    cv.ramp(rings, 0.55 - 0.2 * u, stone, soft=0.5)
    cv.fill(joints, 'stone:1')
    # 拱腹阴影（拱洞内沿）
    cv.fill(edge(bridge, 0, 1) & (cv.yy < water), 'INK')
    cv.fill(shift(edge(bridge, 0, 1), 0, -1) & bridge & (cv.yy < water) & (cv.yy > deck_bot), 'stone:1')
    # 桥面线脚
    cv.fill(bridge & (cv.yy == deck_top), 'stone:5')
    cv.fill(bridge & (cv.yy == deck_bot), 'stone:1')
    cv.fill(bridge & (cv.yy == deck_bot - 1), 'stone:4')
    # 栏杆
    rail = rect_mask(-1, 58, 320, 59)
    for rx in range(0, 320, 5):
        rail |= rect_mask(rx, 60, rx + 1, 63)
    rail &= ~gap & ~((cv.xx > 122) & (cv.xx < 198))
    cv.fill(outline(rail) & (cv.yy < 64), 'INK')
    cv.fill(rail, 'stone:3')
    cv.fill(rail & (cv.yy == 58), 'stone:5')
    # 桥墩的分水尖 + 水线
    for (pa, wa) in piers[1:-1]:
        cut = poly_mask([(pa - wa / 2.0, water - 12), (pa, water - 18), (pa + wa / 2.0, water - 12), (pa + wa / 2.0, water), (pa - wa / 2.0, water)])
        cv.ramp(cut & ~gap, 0.5 - 0.2 * np.clip((cv.xx - pa + wa / 2.0) / wa, 0, 1), stone, soft=0.5)
        cv.fill(rect_mask(pa - wa / 2.0 - 1, water, pa + wa / 2.0 + 1, water), 'mist:3')
    # 断面：暗色断茬 + 悬着的碎石
    brk = (edge(bridge, 1, 0) | edge(bridge, -1, 0)) & (cv.xx > 118) & (cv.xx < 202)
    cv.fill(dilate(brk, 1) & bridge & (cv.t4 > 0.3), 'stone:1')
    cv.fill(brk, 'INK')
    for (dx_, dy_) in [(137, 80), (184, 84), (140, 90), (181, 77)]:
        cv.fill(rect_mask(dx_, dy_, dx_ + 1, dy_ + 1), 'stone:2')
        cv.dot(dx_ + 1, dy_ + 1, 'INK')
    # 河中碎石堆
    rng = np.random.default_rng(3)
    for _ in range(11):
        rx, ry = rng.uniform(126, 194), rng.uniform(106, 118)
        rw_ = rng.uniform(4, 9)
        rock_m = ellipse_mask(rx, ry, rw_, rw_ * 0.55) & (cv.yy <= ry + 1)
        cv.fill(outline(rock_m) & (cv.yy <= ry + 1), 'INK')
        cv.ramp(rock_m, 0.6 - 0.35 * np.clip((cv.xx - rx + rw_) / (2 * rw_), 0, 1), stone, soft=0.5)
        cv.fill(rect_mask(rx - rw_, ry + 1, rx + rw_, ry + 1) & (cv.t4 > 0.3), 'mist:3')
    # 倒影（桥的镜像，被波纹打断）
    for y in range(water + 1, 160):
        src = water - (y - water) * 1.25
        if src < deck_top - 6:
            break
        row = (bridge | rail)[int(src)]
        wob = int(round(math.sin(y * 0.9) * 1.2))
        row = np.roll(row, wob)
        if (y - water) % 4 == 3:
            cv.px[y][row & (np.arange(cv.w) % 2 == 0)] = C('overcast:0')
        else:
            cv.px[y][row] = C('INK')
    # 波纹
    rng = np.random.default_rng(6)
    for _ in range(46):
        y = rng.uniform(86, 146)
        x = rng.uniform(0, 320)
        L = int(3 + (y - 84) / 8 + rng.uniform(0, 5))
        c = 'mist:3' if y < 104 else ('mist:1' if y < 128 else 'mist:0')
        for k2 in range(L):
            cv.dot(x + k2, y, c)
    # 河雾
    fog = fbm2d(cv.w, cv.h, 60, 5, 12, 3)
    for (cy, amp, col) in [(92, 0.5, 'mist:4'), (112, 0.45, 'mist:3'), (80, 0.35, 'mist:4')]:
        band = np.exp(-((cv.yy - cy) / 5.0) ** 2) * amp + fog * 0.3
        cv.fill((band > cv.t4 * 0.9 + 0.16) & (np.abs(cv.yy - cy) < 7) & ~(bridge & (cv.yy < cy - 3)) & ~(wb & (cy < 90)), col)
    # 断口处的残烟
    rng = np.random.default_rng(8)
    x = 160.0
    for k2 in range(56):
        y = 104 - k2
        x += math.sin(k2 * 0.2) * 0.6 + 0.25
        if rng.random() < 0.75 - k2 * 0.011:
            cv.dot(x, y, 'overcast:6' if k2 < 26 else 'overcast:5')
    # 近岸：礁石与芦苇
    bank = height_mask(148 + fbm1d(cv.w, 16, 2, 3) * 4)
    reeds = Mask(cv.w, cv.h, 4)
    for (cx, n) in [(10, 9), (34, 7), (58, 5), (254, 6), (280, 9), (306, 8)]:
        for k2 in range(n):
            bx = cx + rng.uniform(-6, 6)
            L = rng.uniform(12, 30)
            lean = rng.uniform(-0.35, 0.45)
            tip = (bx + lean * L, 150 - L)
            reeds.poly([(bx - 1.1, 151), tip, (bx + 1.1, 151)])
            if rng.random() < 0.45:
                reeds.ellipse(bx + lean * L * 0.8, 150 - L * 0.8, 1.2, 3)
    rm = reeds.get()
    cv.fill(bank | rm, 'INK')
    cv.fill(edge(rm, -1, 0) & (cv.yy < 146), 'overcast:1')
    return cv


# ===========================================================================
# 9. 河东村庄的难民营（白天）
# ===========================================================================
def tent(cv, cx, base, w, h, canvas_r, seed, t=0.55, open_side=1, patch=True, stripe=None):
    """A 字帐篷：三角形正面 + 右侧斜面 + 门帘开口 + 顶杆；stripe=(色, 间距) 画条纹布。"""
    mm = Mask(cv.w, cv.h, 4)
    mm.poly([(cx - w / 2, base), (cx, base - h), (cx + w / 2, base)])
    front = mm.get()
    ms = Mask(cv.w, cv.h, 4)
    ms.poly([(cx, base - h), (cx + w * 0.75, base - h + 3), (cx + w * 0.75 + w / 2, base), (cx + w / 2, base)])
    sidem = ms.get() & ~front
    allm = front | sidem
    cv.fill(outline(allm) & (cv.yy < base + 1), 'INK')
    u = np.clip((cv.xx - (cx - w / 2)) / w, 0, 1)
    cv.ramp(front, t - 0.12 * u, canvas_r, soft=0.5)
    cv.ramp(sidem, t - 0.22, canvas_r, soft=0.5)
    if stripe:
        col, gap = stripe
        cv.fill(sidem & (((cv.xx - cv.yy * 0.1).astype(int) % gap) < 2), col)
    rng = np.random.default_rng(seed)
    if patch:
        px_, py_ = cx + rng.uniform(-w * 0.2, w * 0.05), base - h * rng.uniform(0.3, 0.45)
        cv.fill(rect_mask(px_, py_, px_ + 2, py_ + 2) & front, canvas_r[max(1, len(canvas_r) - 3)])
    door = poly_mask([(cx, base - h * 0.62), (cx - w * 0.16, base), (cx + w * 0.16, base)])
    cv.fill(door, 'INK2')
    cv.fill(edge(door, -1, 0), canvas_r[-1])
    cv.fill(rect_mask(cx, base - h - 3, cx, base - h), 'wood:1')
    cv.fill(edge(front, 0, -1) & (u < 0.5), canvas_r[-1])
    # 拉绳
    if w > 20:
        draw_polyline(cv, [(cx - w / 2 - 4, base), (cx - 1, base - h + 1)], canvas_r[1])
    return allm


def person(cv, x, base, cloth, seed=0, skin='skin:3', hair='hair_brown:2', dark='INK2', h=8):
    """远景小人（约 3×8）：头、身、腿，朝左受光。"""
    x, base = int(x), int(base)
    cv.fill(rect_mask(x, base - 1, x, base), dark)
    cv.fill(rect_mask(x + 2, base - 1, x + 2, base), dark)
    cv.fill(rect_mask(x, base - h + 3, x + 2, base - 2), C(cloth))
    cv.fill(rect_mask(x + 2, base - h + 3, x + 2, base - 2), dark)
    cv.dot(x + 1, base - h + 2, skin)
    cv.dot(x + 1, base - h + 1, hair)
    cv.dot(x, base - h + 2, hair)


@scene('第二章·战后：河东村庄的难民营（白天、帐篷、炊烟）')
def bg_refugee_camp():
    cv = Canvas()
    cv.light = vignette(cv, 0.1)
    sky = rp('day:1', 'day:2', 'day:3', 'day:4', 'day:5', 'day:6')
    cv.ramp(None, np.clip(vgrad(cv, -10, 84), 0, 1), sky, soft=0.55)
    rng = np.random.default_rng(3)
    for (cx, cy, n, sz) in [(58, 22, 9, 1.0), (214, 14, 11, 1.1), (300, 40, 5, 0.7), (140, 44, 4, 0.6)]:
        items = [(cx + rng.uniform(-26, 26) * sz, cy + rng.uniform(-3, 5) * sz, rng.uniform(5, 10) * sz) for _ in range(n)]
        items.sort(key=lambda it: it[1])
        cloud = puffs(cv, items, rp('day:4', 'day:5', 'day:6', 'cloth_white:3', 'cloth_white:4'), up=0.5, down=-0.15, gain=0.2)
        flat = cloud & (cv.yy > cy + 4 * sz)
        cv.fill(flat, 'day:5')
    # 远山与丘陵（空气透视：越远越蓝）
    far = height_mask(ridge_line(cv.w, 70, 12, 80, 5, 3))
    cv.ramp(far, 0.5, rp('day:2', 'day:3', 'day:4', 'mist:4'), soft=0.5)
    cv.fill(edge(far, 0, -1), 'day:5')
    hills = height_mask(ridge_line(cv.w, 82, 7, 60, 6, 3))
    cv.ramp(hills, 0.5 + 0.25 * (1 - np.clip(vgrad(cv, 68, 96), 0, 1)), rp('forest:1', 'forest:2', 'forest:3', 'grass:2', 'grass:3', 'mist:4'), soft=0.5)
    # 远处的林带
    wood_m = height_mask(conifer_line(cv.w, 90, 5, 10, 5, 17)) & ~height_mask(np.full(cv.w, 200.0))
    trees = np.zeros((cv.h, cv.w), bool)
    for (tx, th, sd) in [(14, 18, 1), (30, 14, 2), (46, 16, 3), (118, 12, 4), (188, 14, 5), (304, 18, 6), (318, 14, 7)]:
        trees = round_tree(trees, tx, 94, th, sd)
    tm = (wood_m & (cv.xx < 90)) | trees
    cv.ramp(tm, 0.55 - 0.3 * np.clip(vgrad(cv, 76, 94), 0, 1), rp('forest:0', 'forest:1', 'forest:2', 'forest:3', 'forest:4'), soft=0.5)
    cv.fill((edge(tm, 0, -1) | edge(tm, -1, 0)) & (cv.t4 > 0.25), 'grass:4')
    # 河东的村庄（右侧）：民居 + 小礼拜堂
    # 小教堂：侧屋 + 细高钟楼（远景比例）
    cw_r = rp('INK', 'stone:2', 'stone:3', 'stone:4', 'cloth_white:3')
    cr_r = rp('INK', 'roof_red:1', 'roof_red:2', 'roof_red:3', 'roof_red:4')
    draw_house(cv, 238, 94, 30, 10, 7, 'side', 'normal', 44, cw_r, cr_r, beam='stone:2', win_lit=False, t_wall=0.62, t_roof=0.55)
    twr = rect_mask(248, 64, 256, 94)
    cv.fill(outline(twr), 'INK')
    cv.ramp(twr, 0.66 - 0.4 * np.clip((cv.xx - 248) / 8.0, 0, 1), cw_r, soft=0.5)
    spire = poly_mask([(246.5, 65), (252, 50), (257.5, 65)])
    cv.fill(outline(spire), 'INK')
    cv.ramp(spire, 0.55 + np.where(cv.xx < 252, 0.12, -0.14), cr_r, soft=0.5)
    cv.fill(rect_mask(251, 70, 253, 75), 'INK2')
    cv.dot(252, 72, 'gold:3')
    cv.dot(252, 49, 'gold:3')
    for i, (x, base, w, wh, rh, kind) in enumerate([(200, 95, 20, 9, 8, 'gable'), (272, 96, 24, 9, 6, 'side'), (300, 95, 18, 9, 8, 'gable')]):
        draw_house(cv, x, base, w, wh, rh, kind, 'normal', 40 + i, rp('INK', 'earth:2', 'earth:3', 'earth:4', 'cloth_white:3'),
                   rp('INK', 'roof_red:1', 'roof_red:2', 'roof_red:3', 'roof_red:4'), beam='wood:1', win_lit=False, t_wall=0.62, t_roof=0.55)
    # 营地草地（有踩秃的土块和草丛）
    field = height_mask(94 + fbm1d(cv.w, 30, 7, 2) * 1.5)
    g = fbm2d(cv.w, cv.h, 10, 4, 8, 3)
    cv.ramp(field, 0.6 - 0.34 * np.clip(vgrad(cv, 94, 150), 0, 1) + 0.12 * g, rp('forest:0', 'forest:1', 'forest:2', 'grass:1', 'grass:2', 'grass:3', 'grass:4'), soft=0.5)
    bare = field & (fbm2d(cv.w, cv.h, 14, 5, 9, 3) > 0.38) & (cv.yy > 104)
    cv.ramp(bare, 0.55 - 0.3 * np.clip(vgrad(cv, 96, 150), 0, 1), rp('earth:0', 'earth:1', 'earth:2', 'earth:3'), soft=0.5)
    tufts = field & (fbm2d(cv.w, cv.h, 2, 1.5, 10, 2) > 0.45) & ~bare
    cv.fill(tufts, 'forest:1')
    cv.fill(shift(tufts, 0, -1) & ~tufts & field & ~bare & (cv.t4 > 0.5), 'grass:3')
    path = poly_mask([(152, 96), (164, 96), (190, 120), (212, 180), (110, 180), (140, 120)])
    cv.ramp(path, 0.6 - 0.28 * np.clip(vgrad(cv, 96, 150), 0, 1), rp('earth:0', 'earth:1', 'earth:2', 'earth:3', 'earth:4'), soft=0.5)
    cv.fill(edge(path, -1, 0) | edge(path, 1, 0), 'grass:1')
    # 帐篷（颜色不一：各家凑出来的布）
    canvas_a = rp('INK', 'cloth_brown:2', 'cloth_brown:3', 'cloth_brown:4', 'earth:4', 'cloth_white:3')
    canvas_b = rp('INK', 'stone:2', 'stone:3', 'stone:4', 'cloth_white:2', 'cloth_white:3')
    canvas_c = rp('INK', 'cloth_olive:2', 'cloth_olive:3', 'cloth_olive:4', 'earth:4', 'cloth_white:3')
    tents = [(128, 102, 18, 13, 2, canvas_b, None), (184, 101, 16, 12, 3, canvas_c, None), (98, 106, 22, 17, 1, canvas_a, None),
             (222, 106, 22, 17, 4, canvas_a, ('cloth_crimson:3', 5)), (58, 112, 28, 22, 5, canvas_c, None),
             (262, 114, 28, 22, 6, canvas_b, None), (18, 124, 34, 28, 7, canvas_a, None), (300, 126, 34, 28, 8, canvas_a, ('cloth_navy:3', 6))]
    for (cx, base, w, h, sd, cr, st) in tents:
        tent(cv, cx, base, w, h, cr, sd, stripe=st)
    # 公用凉棚（四根柱子撑一块布）
    awn = poly_mask([(144, 104), (176, 102), (180, 108), (140, 110)])
    cv.fill(outline(awn), 'INK')
    cv.ramp(awn, 0.62 - 0.2 * np.clip(vgrad(cv, 102, 110), 0, 1), canvas_a, soft=0.5)
    for px_ in (142, 178):
        cv.fill(rect_mask(px_, 108, px_, 118), 'wood:1')
    cv.fill(rect_mask(146, 110, 174, 118), 'INK2')
    cv.fill(rect_mask(150, 114, 170, 116), 'wood:2')
    # 炊火 + 三脚架吊锅 + 炊烟
    for (sx, sy, sd) in [(114, 116, 1), (206, 114, 2), (78, 124, 3), (246, 124, 4)]:
        draw_polyline(cv, [(sx - 4, sy + 1), (sx, sy - 8)], 'wood:1')
        draw_polyline(cv, [(sx + 4, sy + 1), (sx, sy - 8)], 'wood:1')
        cv.fill(rect_mask(sx - 2, sy - 5, sx + 2, sy - 3), 'iron:1')
        cv.fill(rect_mask(sx - 2, sy - 5, sx + 2, sy - 5), 'iron:3')
        cv.fill(rect_mask(sx - 3, sy + 1, sx + 3, sy + 1), 'stone:2')
        cv.dot(sx, sy, 'fire:3')
        cv.dot(sx - 1, sy, 'fire:2')
        cv.dot(sx + 1, sy, 'fire:2')
        x = float(sx)
        for k in range(66):
            y = sy - 9 - k
            x += math.sin(k * 0.15 + sd) * 0.45 + 0.28
            wdt = 2 + (k > 14) + (k > 34)
            for d in range(wdt):
                if k > 40 and (int(x) + d + y) % 2:
                    continue
                if k > 54 and (int(x) + d + y) % 4:
                    continue
                cv.dot(x + d, y, 'cloth_white:4' if (d == 0 and k < 30) else ('cloth_white:3' if k < 44 else 'day:6'))
    # 晾衣绳 + 衣物
    pts = catenary(86, 94, 118, 92, 4)
    draw_polyline(cv, pts, 'wood:1')
    for (i, c) in [(6, 'cloth_white:3'), (14, 'cloth_sky:3'), (22, 'cloth_white:4'), (28, 'cloth_crimson:3')]:
        x, y = pts[i]
        cv.fill(rect_mask(x, y + 1, x + 2, y + 5), c)
    # 手推车 + 木箱
    cart = rect_mask(236, 128, 256, 132)
    cv.fill(outline(cart), 'INK')
    cv.fill(cart, 'wood:2')
    cv.fill(rect_mask(236, 128, 256, 128), 'wood:3')
    wheel = ellipse_mask(242, 134, 3, 3) & ~ellipse_mask(242, 134, 1.2, 1.2)
    cv.fill(wheel, 'wood:0')
    draw_polyline(cv, [(256, 131), (266, 136)], 'wood:1')
    for (bx, by) in [(188, 122), (194, 122), (191, 118)]:
        b = rect_mask(bx, by - 4, bx + 5, by)
        cv.fill(outline(b), 'INK')
        cv.fill(b, 'wood:2')
        cv.fill(rect_mask(bx, by - 4, bx + 5, by - 4), 'wood:3')
    # 人
    people = [(108, 106, 'cloth_brown:3'), (120, 112, 'cloth_olive:3'), (152, 118, 'cloth_sky:2'), (158, 118, 'cloth_crimson:2'),
              (166, 117, 'cloth_brown:4'), (200, 112, 'cloth_green:3'), (212, 120, 'cloth_white:1'), (234, 116, 'cloth_brown:3'),
              (72, 130, 'cloth_olive:3'), (88, 126, 'cloth_navy:3'), (250, 136, 'cloth_brown:4'), (140, 130, 'cloth_green:3')]
    for i, (px_, py_, c) in enumerate(people):
        person(cv, px_, py_, c, seed=i)
    return cv


# ===========================================================================
# 10. 静语修道院外景（夜、细雨、薄雾）
# ===========================================================================
def cypress(m, x, base, h, w=None):
    """柏树剪影：细长火焰形。"""
    w = w or max(3, h * 0.2)
    mm = Mask(m.shape[1], m.shape[0], 4)
    pts_l, pts_r = [], []
    for i in range(13):
        s = i / 12.0
        y = base - s * h
        hw = w / 2 * math.sin(min(1.0, (1 - s) * 1.25 + 0.05) * math.pi * 0.62) * (1.2 - s * 0.5)
        pts_l.append((x - hw, y))
        pts_r.append((x + hw, y))
    mm.poly(pts_l + pts_r[::-1])
    return m | mm.get()


@scene('第三章：静语修道院外景（夜、细雨薄雾、钟楼、围墙）')
def bg_monastery_ext():
    cv = Canvas()
    cv.light = vignette(cv, 0.16) + radial(cv, 60, 6, 130, 1.4) * 0.22
    sky = rp('night:0', 'night:1', 'night:2', 'night:3', 'night:4', 'mist:1')
    cv.ramp(None, np.clip(vgrad(cv, -10, 110), 0, 1) ** 1.1, sky, soft=0.55)
    # 雨云（月亮躲在左上方云后，云边被照亮）
    rng = np.random.default_rng(21)
    items = [(rng.uniform(-10, 330), rng.uniform(-4, 26), rng.uniform(9, 16)) for _ in range(24)]
    items.sort(key=lambda it: it[1])
    puffs(cv, items, rp('night:0', 'night:1', 'night:2', 'night:3', 'night:5', 'night:6'), up=0.35, down=-0.1, gain=0.8)
    # 远山
    far = height_mask(ridge_line(cv.w, 100, 14, 90, 31, 3))
    cv.ramp(far, 0.45, rp('night:1', 'night:2', 'night:3', 'mist:1'), soft=0.5)
    # 岩崖
    xs = np.arange(cv.w)
    crag_top = 110 - 16 * np.exp(-((xs - 160) / 80.0) ** 2) + fbm1d(cv.w, 9, 4, 3) * 2
    crag = height_mask(crag_top)
    u = np.clip((cv.xx - 60) / 200.0, 0, 1)
    rock_face(cv, crag, 17, rp('INK', 'INK2', 'night:1', 'night:2', 'stone:1', 'stone:2'), 0.5 - 0.3 * u - 0.25 * np.clip(vgrad(cv, 96, 140), 0, 1),
              slope=0.3, spacing=9, snow=('night:2', 'night:3'), ledge_frac=0.1)
    wall = rp('INK', 'night:1', 'night:2', 'stone:1', 'stone:2', 'stone:3')
    roof = rp('INK', 'roof_blue:0', 'roof_blue:1', 'night:3', 'night:4')
    # 两翼僧舍
    for (x, w, wh, rh, sd) in [(62, 44, 18, 11, 1), (212, 46, 20, 11, 2)]:
        h_ = draw_house(cv, x, 96, w, wh, rh, 'side', 'normal', sd, wall, roof, beam='night:1', t_wall=0.5, win_lit=True)
        cv.fill(rim_edges(h_['roof'])[0], 'night:5')
    # 礼拜堂中殿
    mw, mr = Mask(cv.w, cv.h, 4), Mask(cv.w, cv.h, 4)
    side_house(mw, mr, 104, 96, 104, 32, 18, over=2, slope=0.45)
    nave, nroof = mw.get(), mr.get()
    cv.fill(outline(nave | nroof), 'INK')
    un = np.clip((cv.xx - 104) / 104.0, 0, 1)
    bh_, bv_ = brick_lines(cv.xx, cv.yy, 8, 5)
    cv.ramp(nave, 0.55 - 0.3 * un - 0.08 * (bh_ | bv_), wall, soft=0.5)
    cv.ramp(nroof, 0.5 - 0.3 * np.clip(vgrad(cv, 46, 64), 0, 1), roof, soft=0.5)
    cv.fill(rim_edges(nroof)[0], 'night:6')
    # 扶壁 + 尖拱窗
    for bx in (110, 128, 186, 200):
        cv.fill(poly_mask([(bx, 70), (bx + 3, 70), (bx + 7, 96), (bx, 96)]), 'night:1')
        cv.fill(rect_mask(bx, 70, bx, 96), 'stone:2')
    for wx in (117, 136, 176, 192):
        m = rect_mask(wx, 74, wx + 4, 90) & ~rect_mask(wx, 74, wx, 74) & ~rect_mask(wx + 4, 74, wx + 4, 74)
        lit = wx in (117, 176, 192)
        cv.fill(m, 'fire:2' if lit else 'INK')
        cv.fill(m & (cv.yy < 78), 'fire:3' if lit else 'INK')
        cv.fill(m & (cv.xx == wx + 2), 'INK' if lit else 'INK')
    # 钟楼（高耸，居中）
    tw = rect_mask(146, 30, 172, 96)
    ut = np.clip((cv.xx - 146) / 26.0, 0, 1)
    bh2, bv2 = brick_lines(cv.xx - 146, cv.yy, 9, 5)
    cv.fill(outline(tw), 'INK')
    cv.ramp(tw, 0.62 - 0.42 * ut - 0.08 * (bh2 | bv2), wall, soft=0.5)
    sp = poly_mask([(143, 31), (159, 1), (175, 31)])
    cv.fill(outline(sp), 'INK')
    cv.ramp(sp, 0.5 + np.where(cv.xx < 159, 0.12, -0.15), roof, soft=0.5)
    cv.fill(rim_edges(sp)[0], 'night:6')
    cv.fill(rim_edges(tw)[1], 'night:5')
    cv.fill(rect_mask(146, 30, 172, 32), 'stone:2')
    cv.fill(rect_mask(146, 30, 172, 30), 'night:5')
    cv.dot(159, 0, 'gold:3')
    cv.dot(159, -1, 'gold:3')
    # 钟洞与钟
    bell = rect_mask(151, 38, 166, 54) | (ellipse_mask(158.5, 38, 7.5, 4) & (cv.yy <= 38))
    cv.fill(bell, 'INK')
    cv.fill(rect_mask(154, 42, 162, 50), 'gold:1')
    cv.fill(rect_mask(155, 42, 157, 49), 'gold:2')
    cv.fill(rect_mask(153, 50, 163, 51), 'gold:1')
    cv.fill(rect_mask(158, 39, 158, 41), 'iron:2')
    # 塔身一扇亮窗 + 圆窗
    cv.fill(rect_mask(157, 62, 160, 68), 'fire:2')
    cv.fill(rect_mask(157, 62, 160, 63), 'fire:3')
    rw = ellipse_mask(158.5, 78, 3.5, 3.5)
    cv.fill(dilate(rw, 1) & ~rw, 'stone:2')
    cv.fill(rw, 'INK')
    # 围墙 + 门
    enc = rect_mask(34, 96, 286, 114)
    for x in range(34, 286, 6):
        enc |= rect_mask(x, 93, x + 2, 96)
    cv.fill(outline(enc), 'INK')
    bh3, bv3 = brick_lines(cv.xx, cv.yy - 96, 10, 5)
    cv.ramp(enc, 0.45 - 0.2 * np.clip((cv.xx - 34) / 252.0, 0, 1) - 0.08 * (bh3 | bv3), wall, soft=0.5)
    cv.fill(rim_edges(enc)[0], 'night:5')
    gate = rect_mask(151, 100, 166, 114) | (ellipse_mask(158.5, 100, 7.5, 5) & (cv.yy <= 100))
    cv.fill(gate, 'INK')
    cv.fill(outline(gate) & enc, 'stone:2')
    cv.fill(gate & (cv.xx == 158), 'wood:0')
    # 门灯
    cv.dot(147, 101, 'INK')
    cv.fill(rect_mask(146, 102, 148, 104), 'fire:3')
    cv.dot(147, 105, 'fire:1')
    # 柏树
    cyp = np.zeros((cv.h, cv.w), bool)
    for (x, h) in [(24, 62), (38, 48), (292, 64), (306, 50), (98, 34), (222, 32)]:
        cyp = cypress(cyp, x, 116, h)
    cv.fill(cyp, 'INK')
    cv.fill(edge(cyp, -1, 0) & (cv.t4 > 0.3), 'night:2')
    # 薄雾带（绕在崖脚）
    fog = fbm2d(cv.w, cv.h, 70, 5, 13, 3)
    for (cy, amp, col) in [(119, 0.75, 'mist:1'), (128, 0.7, 'mist:0')]:
        band = np.exp(-((cv.yy - cy) / 4.0) ** 2) * amp + fog * 0.4
        cv.fill((band > cv.t8 * 0.6 + 0.3) & (np.abs(cv.yy - cy) < 7), col)
    cv.fill(height_mask(134 + fbm1d(cv.w, 12, 9, 2) * 3), 'INK')
    # 细雨
    rain(cv, 240, 5, col='night:4', col2='night:5', length=(4, 7), slope=0.3)
    return cv


# ===========================================================================
# 11. 修道院礼拜堂内部（烛光、彩色玻璃、祭坛）
# ===========================================================================
def candle(cv, x, y, h=4, wax='cloth_white:3', wax2='cloth_white:1'):
    cv.fill(rect_mask(x, y - h + 1, x, y), wax)
    cv.fill(rect_mask(x + 1, y - h + 1, x + 1, y), wax2)
    cv.dot(x, y - h - 1, 'fire:3')
    cv.dot(x, y - h - 2, 'fire:4')
    cv.dot(x + 1, y - h - 1, 'fire:2')


@scene('第三章·战后：修道院礼拜堂内部（烛光、彩色玻璃窗、祭坛）')
def bg_chapel():
    cv = Canvas()
    vx, vy = 160, 60
    b0, b1, by = 104, 216, 94
    left = poly_mask([(-1, -1), (b0, -1), (b0, by), (-1, vy + (by - vy) * (vx + 1) / (vx - b0))])
    right = poly_mask([(b1, -1), (320, -1), (320, vy + (by - vy) * (vx + 1) / (vx - b0)), (b1, by)])
    back = rect_mask(b0, 0, b1, by - 1)
    floor = ~(left | right | back)
    # 烛光光源
    cands = [(160, 72, 1.0), (130, 84, 0.8), (190, 84, 0.8), (112, 88, 0.6), (208, 88, 0.6), (70, 100, 0.5), (250, 100, 0.5)]
    light = vignette(cv, 0.2)
    for (cx, cy, s) in cands:
        light += radial(cv, cx, cy, 70 * s, 1.2) ** 1.4 * 0.5 * s
    cv.light = light
    wallr = rp('INK', 'INK2', 'stone:0', 'stone:1', 'rock:1', 'rock:2', 'leather:3', 'gold:3')
    hl, vl = brick_lines(cv.xx - b0, cv.yy, 12, 6)
    cv.ramp(back, 0.18 - 0.08 * (hl | vl), wallr, soft=0.5)
    k = np.maximum(np.abs(cv.xx - vx) / float(vx - b0), 1e-3)
    v = (cv.yy - vy) / k
    z = 10.0 / k
    hl2, vl2 = brick_lines(z * 6, v, 8, 6)
    for sm in (left, right):
        cv.ramp(sm, 0.2 - 0.08 * (hl2 | vl2), wallr, soft=0.5)
    kf = np.maximum((cv.yy - vy) / float(by - vy), 1e-3)
    uf = (cv.xx - vx) / kf
    zf = 10.0 / kf
    tile = ((np.floor(uf / 16) + np.floor(zf * 1.2)) % 2)
    cv.ramp(floor, 0.18 + 0.05 * tile, wallr, soft=0.5)
    # 彩色玻璃长窗（三扇）
    def lancet(x0, y0, w, h):
        mm = Mask(cv.w, cv.h, 4)
        cx = x0 + w / 2.0
        mm.poly([(x0, y0 + w * 0.6), (cx, y0), (x0 + w, y0 + w * 0.6), (x0 + w, y0 + h), (x0, y0 + h)])
        return mm.get()
    glass = [('glass_b', 'glass_r', 'glass_y'), ('glass_r', 'glass_y', 'glass_b'), ('glass_g', 'glass_v', 'glass_y')]
    for i, (x0, y0, w, h) in enumerate([(118, 16, 16, 50), (150, 6, 20, 62), (186, 16, 16, 50)]):
        wm = lancet(x0, y0, w, h)
        fr = dilate(wm, 2) & ~wm
        cv.ramp(fr, 0.3, wallr, soft=0.5)
        cv.fill(outline(dilate(wm, 2)), 'INK')
        cols = glass[i]
        # 菱形分格的彩色玻璃
        cell = (np.floor((cv.xx - x0 + cv.yy) / 5) + np.floor((cv.xx - x0 - cv.yy) / 5)) % 3
        for ci in range(3):
            g = cols[ci]
            m = wm & (cell == ci)
            cv.ramp(m, 0.55 - 0.35 * np.clip(vgrad(cv, y0, y0 + h), 0, 1) + 0.1 * (cv.t4 > 0.8), R(g), soft=0.5, gain=0)
        lead = wm & ((((cv.xx - x0 + cv.yy) % 5) == 0) | (((cv.xx - x0 - cv.yy) % 5) == 0))
        cv.fill(lead, 'INK')
        cv.fill(wm & (cv.xx == int(x0 + w / 2)), 'INK')
    # 彩窗投在地上的色斑
    for (px_, py_, g, g2) in [(148, 104, 'glass_b:1', 'glass_b:2'), (160, 110, 'glass_r:1', 'glass_r:2'), (172, 104, 'glass_y:1', 'glass_y:2')]:
        spot = ellipse_mask(px_, py_, 9, 3.5) & floor
        cv.fill(spot & (cv.t4 > 0.3), g)
        cv.fill(ellipse_mask(px_, py_, 5, 1.8) & floor & (cv.t4 > 0.55), g2)
    # 祭坛
    alt = rect_mask(134, 74, 186, 90)
    cv.ramp(alt, 0.4 - 0.2 * np.clip((cv.xx - 134) / 52.0, 0, 1), wallr, soft=0.5)
    cloth = rect_mask(132, 72, 188, 76) | rect_mask(150, 76, 170, 88)
    cv.ramp(cloth, 0.8 - 0.3 * np.clip((cv.xx - 132) / 56.0, 0, 1), rp('cloth_white:0', 'cloth_white:1', 'cloth_white:2', 'cloth_white:3', 'cloth_white:4'), soft=0.5, gain=0.3)
    cv.fill(rect_mask(150, 86, 170, 86), 'gold:3')
    stamp(cv, DEER, 154, 77, 'gold:3')
    cv.fill(outline(alt | cloth), 'INK')
    # 台阶
    for i, (x0, x1, y0, y1) in enumerate([(124, 196, 90, 93), (116, 204, 93, 97)]):
        m = rect_mask(x0, y0, x1, y1)
        cv.ramp(m, 0.36, wallr, soft=0.5)
        cv.fill(rect_mask(x0, y0, x1, y0), 'rock:2')
    # 祭坛上的烛台与蜡烛
    for x in (140, 146, 174, 180):
        cv.fill(rect_mask(x, 68, x, 72), 'gold:2')
        cv.fill(rect_mask(x - 1, 72, x + 1, 72), 'gold:3')
        candle(cv, x, 67, 3)
    cv.fill(rect_mask(156, 64, 164, 72) & ~rect_mask(157, 64, 163, 67), 'gold:2')
    cv.fill(rect_mask(159, 60, 161, 72), 'gold:3')
    candle(cv, 160, 59, 4)
    candle(cv, 157, 63, 3)
    candle(cv, 163, 63, 3)
    # 高烛架
    for (x, y, hgt) in [(112, 94, 20), (208, 94, 20), (70, 112, 30), (250, 112, 30)]:
        cv.fill(rect_mask(x, y - hgt, x + 1, y), 'gold:1')
        cv.fill(rect_mask(x, y - hgt, x, y), 'gold:3')
        cv.fill(rect_mask(x - 3, y, x + 4, y + 1), 'gold:1')
        cv.fill(rect_mask(x - 3, y - hgt, x + 4, y - hgt + 1), 'gold:2')
        for dx in (-3, 0, 3):
            candle(cv, x + dx, y - hgt - 1, 3)
    # 侧墙壁柱与拱
    pil = rp('INK', 'INK2', 'stone:0', 'stone:1', 'rock:1', 'rock:2', 'leather:3')
    for side in (-1, 1):
        for (xb, w, yb) in [(94, 6, 98), (70, 11, 112), (26, 22, 136)]:
            x0 = xb - w // 2 if side < 0 else 320 - xb - w // 2
            pillar(cv, x0, x0 + w, -1, yb, pil, 0.3, light_from=1 if side < 0 else -1)
    # 长椅（左右两排，近大远小；看到的是椅背，顶沿被祭坛烛光勾亮）
    pew = rp('INK', 'wood:0', 'wood:1', 'wood:2', 'wood:3')
    for i in range(5):
        k = 1.0 + i * 0.42
        yb = 104 + i * 12 + i * i * 1.6
        aisle = 11 * k
        length = 46 * k
        for side in (-1, 1):
            xa = 160 + side * aisle
            xb = 160 + side * (aisle + length)
            x0, x1 = min(xa, xb), max(xa, xb)
            back_m = rect_mask(x0, yb - 5 * k, x1, yb - 1)
            cv.fill(outline(back_m), 'INK')
            cv.ramp(back_m, 0.34 - 0.12 * np.clip(vgrad(cv, yb - 5 * k, yb), 0, 1), pew, soft=0.5)
            cv.fill(edge(back_m, 0, -1), 'wood:3')
            cv.fill(rect_mask(x0, yb - 2 * k, x1, yb - 2 * k), 'wood:0')
            # 靠过道一端的扶手板（圆顶）
            ex = xa if side < 0 else xa - 2 * k
            end = rect_mask(ex - k, yb - 8 * k, ex + k, yb + 2 * k) | ellipse_mask(ex, yb - 8 * k, 1.6 * k, 1.6 * k)
            cv.fill(outline(end), 'INK')
            cv.ramp(end, 0.42 - 0.2 * np.clip(vgrad(cv, yb - 10 * k, yb), 0, 1), pew, soft=0.5)
            cv.fill(edge(end, 0, -1) | edge(end, side, 0) & (cv.yy < yb - 4 * k), 'wood:4')
            cv.fill(rect_mask(x0, yb, x1, yb + 1 + i // 2), 'INK')
    embers(cv, 10, 3, (110, 50, 210, 90), cols=('fire:3', 'fire:4'), big=0.0)
    return cv


# ===========================================================================
# 12 / 13. 雪山：风雪山道 / 霜牙关要塞
# ===========================================================================
def snow_mountains(cv, peaks, base, seed, snow_lit, snow_dark, rock_lit=None, rock_dark=None, t=0.5, rock=0.0, rough=2.0):
    """雪山：峰左受光、峰右背光；岩石沿坡向出露成沟壑条纹（不是斑点），越往下岩石越多。返回遮罩。"""
    top = peaks_line(cv.w, peaks, base, seed, rough=rough)
    m = height_mask(top)
    xs = np.arange(cv.w)
    px = np.array([p[0] for p in peaks])
    near = px[np.argmin(np.abs(xs[:, None] - px[None, :]), axis=1)]
    lit = np.broadcast_to((xs < near)[None, :], m.shape)
    depth = np.clip((cv.yy - top[None, :]) / 45.0, 0, 1)
    shade = t + np.where(lit, 0.28, -0.05) - 0.22 * depth
    if rock_lit is not None:
        pad = 160
        g = fbm2d(cv.w + 2 * pad, cv.h, 2.5, 13, seed + 5, 3)
        sheer = np.where(lit, -0.9, 0.9)
        u = np.clip(np.round(cv.xx + (cv.yy - top[None, :]) * sheer).astype(int) + pad, 0, cv.w + 2 * pad - 1)
        gg = g[cv.yy.astype(int), u]
        rk = m & (gg > 0.3 - rock - depth * 0.35 + np.where(lit, 0.08, -0.04)) & (depth > 0.04)
    else:
        rk = np.zeros_like(m)
    sn = m & ~rk
    cv.ramp(sn & lit, shade, snow_lit, soft=0.5)
    cv.ramp(sn & ~lit, shade, snow_dark, soft=0.5)
    if rk.any():
        cv.ramp(rk & lit, shade - 0.1, rock_lit, soft=0.5)
        cv.ramp(rk & ~lit, shade - 0.05, rock_dark, soft=0.5)
        # 岩石上缘压一道雪
        cv.fill(edge(rk, 0, -1) & lit & (cv.t4 > 0.3), snow_lit[-2])
    cv.fill(edge(m, 0, -1) & lit, snow_lit[-1])
    return m


def snowy_pine(m_dark, m_snow, x, base, h, seed):
    """雪松：深绿树冠 + 每层枝上的积雪。"""
    w = h * 0.5
    tiers = max(3, int(h / 6))
    md = Mask(m_dark.shape[1], m_dark.shape[0], 4)
    ms = Mask(m_dark.shape[1], m_dark.shape[0], 4)
    top = base - h
    for k in range(tiers):
        ty = top + (h * 0.88) * k / tiers
        by_ = top + (h * 0.88) * (k + 1.5) / tiers
        hw = w * (0.3 + 0.7 * (k + 1) / tiers) / 2
        md.poly([(x, ty), (x - hw, by_), (x + hw, by_)])
        ms.poly([(x, ty), (x - hw * 0.8, ty + (by_ - ty) * 0.55), (x - hw * 0.2, ty + (by_ - ty) * 0.4), (x + hw * 0.5, ty + (by_ - ty) * 0.5), (x + hw * 0.3, ty + (by_ - ty) * 0.3)])
    md.rect(int(x) - 1, int(base - h * 0.15), int(x), int(base))
    return m_dark | md.get(), m_snow | ms.get()


def draw_pines(cv, spec, dark='forest:0', mid='forest:1'):
    md = np.zeros((cv.h, cv.w), bool)
    msn = np.zeros((cv.h, cv.w), bool)
    for (x, b, h, sd) in spec:
        md, msn = snowy_pine(md, msn, x, b, h, sd)
    cv.fill(outline(md) & (cv.t4 > 0.5), 'mist:1')
    cv.fill(md, dark)
    cv.fill(md & edge(md, -1, 0), mid)
    cv.fill(msn & md, 'snow:3')
    cv.fill(msn & md & edge(msn, 0, -1), 'snow:4')
    cv.fill(msn & md & edge(msn, 0, 1) & (cv.t4 > 0.5), 'snow:1')


def wagon_wreck(cv, x, base):
    """被毁的马车（约 90×40）：侧翻的车厢、断轮、被风扯开的篷布、散落的箱桶，都压着雪。"""
    wood = rp('INK', 'wood:0', 'wood:1', 'wood:2', 'wood:3', 'wood:4')
    # 侧翻车厢：斜放的箱体（底板朝向镜头）
    box = poly_mask([(x, base - 6), (x + 12, base - 32), (x + 64, base - 25), (x + 58, base)])
    cv.fill(outline(box), 'INK')
    cv.ramp(box, 0.62 - 0.35 * np.clip((cv.xx - x) / 64.0, 0, 1), wood, soft=0.5)
    for k in range(1, 6):
        a = k / 6.0
        draw_polyline(cv, [(x + 12 * a, base - 6 - 26 * a), (x + 58 + 6 * a, base - 25 * a)], 'wood:0')
    # 底板上的两条横木 + 断开的车轴
    for a in (0.28, 0.72):
        draw_polyline(cv, [(x + a * 58 + 1, base - 1), (x + 12 + a * 52, base - 31)], 'wood:1')
    cv.fill(rect_mask(x + 18, base - 20, x + 46, base - 18), 'iron:1')
    cv.fill(rect_mask(x + 18, base - 20, x + 46, base - 20), 'iron:3')
    # 立着的断轮（左）
    wx, wy, wr = x - 2, base - 12, 11
    wheel = ellipse_mask(wx, wy, wr, wr) & ~ellipse_mask(wx, wy, wr - 2.2, wr - 2.2)
    wheel &= ~(poly_mask([(wx - 12, wy + 2), (wx - 4, wy + 12), (wx - 12, wy + 12)]))
    spokes = np.zeros_like(wheel)
    for a in range(0, 360, 45):
        if a in (135, 180):
            continue
        for rr in np.arange(1.5, wr - 1.5, 0.5):
            spokes[int(round(wy + math.sin(math.radians(a)) * rr)), int(round(wx + math.cos(math.radians(a)) * rr))] = True
    hub = ellipse_mask(wx, wy, 1.6, 1.6)
    wm = wheel | spokes | hub
    cv.fill(outline(wm), 'INK')
    cv.fill(wm, 'wood:2')
    cv.fill(wm & (cv.xx < wx - 2) & (cv.yy < wy), 'wood:4')
    cv.fill(hub, 'iron:2')
    cv.fill(edge(wheel, 0, -1), 'snow:4')
    # 倒在雪里的轮子（右）
    flat = ellipse_mask(x + 76, base - 1, 11, 3) & ~ellipse_mask(x + 76, base - 1, 7.5, 1.4)
    cv.fill(outline(flat), 'INK')
    cv.fill(flat, 'wood:1')
    cv.fill(flat & (cv.yy < base - 2), 'wood:3')
    # 被风扯开的篷布：挂在车厢上沿，向右飘
    cloth = poly_mask([(x + 14, base - 31), (x + 38, base - 36), (x + 58, base - 31), (x + 78, base - 37), (x + 70, base - 29),
                       (x + 86, base - 26), (x + 66, base - 23), (x + 62, base - 25)])
    cv.fill(outline(cloth), 'INK')
    cv.ramp(cloth, 0.72 - 0.4 * np.clip(vgrad(cv, base - 38, base - 22), 0, 1),
            rp('cloth_white:0', 'cloth_white:1', 'cloth_white:2', 'cloth_white:3'), soft=0.5)
    draw_polyline(cv, [(x + 60, base - 30), (x + 72, base - 34)], 'cloth_white:1')
    # 断掉的车辕
    draw_polyline(cv, [(x + 58, base - 3), (x + 96, base + 2)], 'INK')
    draw_polyline(cv, [(x + 58, base - 4), (x + 96, base + 1)], 'wood:2')
    # 木箱、木桶
    for (bx, by, bw, bh) in [(x + 90, base, 10, 8), (x + 101, base + 1, 8, 6), (x - 24, base + 1, 9, 7)]:
        b = rect_mask(bx, by - bh, bx + bw, by)
        cv.fill(outline(b), 'INK')
        cv.ramp(b, 0.6 - 0.3 * np.clip((cv.xx - bx) / bw, 0, 1), wood, soft=0.5)
        cv.fill(b & ((cv.xx == bx) | (cv.xx == bx + bw) | (cv.yy == by - bh // 2)), 'wood:0')
        cv.fill(rect_mask(bx, by - bh, bx + bw, by - bh), 'snow:4')
    barrel = ellipse_mask(x - 34, base - 2, 6, 3.5)
    cv.fill(outline(barrel), 'INK')
    cv.ramp(barrel, 0.55 - 0.3 * np.clip((cv.xx - x + 40) / 12.0, 0, 1), wood, soft=0.5)
    cv.fill(barrel & ((cv.xx == x - 37) | (cv.xx == x - 31)), 'iron:1')
    # 积雪
    cap = edge(box, 0, -1) | (shift(edge(box, 0, -1), 0, 1) & box & (cv.t4 > 0.35))
    cv.fill(cap, 'snow:4')
    cv.fill(edge(cloth, 0, -1) & (cv.t4 > 0.4), 'snow:4')
    drift = ellipse_mask(x + 30, base + 1, 40, 4) & (cv.yy > base - 2) & ~box
    cv.fill(drift & (cv.yy <= base + 2), 'snow:3')
    cv.fill(edge(drift, 0, -1), 'snow:4')


def rock_face(cv, m, seed, ramp, t, slope=0.45, spacing=11.0, snow=('snow:3', 'snow:4'), ledge_frac=0.2):
    """层状岩壁：沿斜向起伏的岩层，每层上沿压一道断续的积雪，层下有一条阴影。"""
    warp = fbm2d(cv.w, cv.h, 16, 9, seed, 3) * 9 + fbm2d(cv.w, cv.h, 5, 4, seed + 1, 2) * 2.5
    sv = (cv.yy + cv.xx * slope + warp) / spacing
    frac = sv - np.floor(sv)
    brk = fbm2d(cv.w, cv.h, 7, 30, seed + 2, 2)
    cv.ramp(m, t - 0.14 * (frac > 0.78) + 0.04 * (frac < 0.5), ramp, soft=0.5)
    ledge = m & (frac < ledge_frac) & (brk > -0.25)
    cv.fill(ledge, snow[0])
    cv.fill(ledge & edge(ledge, 0, -1), snow[1])
    return ledge


@scene('第四章：风雪中的山道（被毁的马车残骸、风雪）')
def bg_snow_road():
    cv = Canvas()
    cv.light = vignette(cv, 0.1)
    sky = rp('mist:2', 'mist:3', 'mist:4', 'mist:5', 'mist:6')
    cv.ramp(None, np.clip(vgrad(cv, -30, 96), 0, 1), sky, soft=0.6)
    # 风雪里若隐若现的远山（无岩石细节，只有明暗）
    snow_mountains(cv, [(54, 30, 70, 90), (168, 18, 90, 90), (282, 36, 80, 90)], 100, 5,
                   rp('mist:3', 'mist:4', 'mist:5'), rp('mist:2', 'mist:3', 'mist:4'), t=0.35)
    snow_mountains(cv, [(110, 58, 60, 60), (236, 52, 60, 70)], 104, 6,
                   rp('mist:2', 'mist:3', 'mist:4', 'mist:5'), rp('mist:1', 'mist:2', 'mist:3'),
                   rp('mist:1', 'mist:2'), rp('mist:0', 'mist:1'), t=0.4, rock=-0.1)
    # 左侧岩壁（层状岩石 + 雪檐）
    cliff = poly_mask([(-1, 8), (18, 20), (30, 40), (46, 62), (60, 88), (70, 104), (-1, 112)])
    u = np.clip((cv.xx + 10) / 80.0, 0, 1)
    cv.fill(outline(cliff) & (cv.yy < 108), 'stone:0')
    rock_face(cv, cliff, 3, rp('stone:0', 'stone:1', 'stone:2', 'stone:3', 'stone:4'), 0.55 - 0.3 * u)
    cv.fill(edge(cliff, 1, 0) & (cv.t4 > 0.3), 'snow:2')
    # 山坡雪地
    xs = np.arange(cv.w)
    slope_top = 98 + (xs / 320.0) * 8 + fbm1d(cv.w, 30, 7, 3) * 3
    slope = height_mask(slope_top) & ~cliff
    cv.ramp(slope, 0.72 - 0.3 * np.clip(vgrad(cv, 98, 150), 0, 1), rp('snow:0', 'snow:1', 'snow:2', 'snow:3', 'snow:4'), soft=0.5)
    # 山道（被雪埋了一半的车辙）
    road = poly_mask([(20, 180), (96, 132), (150, 112), (230, 104), (330, 101), (330, 106), (238, 110), (168, 120), (122, 140), (80, 180)])
    cv.ramp(road, 0.55 - 0.25 * np.clip(vgrad(cv, 100, 170), 0, 1), rp('snow:0', 'snow:1', 'snow:2', 'snow:3'), soft=0.5)
    for off in (0.3, 0.7):
        pts = [(20 + 60 * off, 180), (96 + 26 * off, 132 + 8 * off), (150 + 18 * off, 112 + 8 * off), (230 + 8 * off, 104 + 6 * off), (330, 101 + 5 * off)]
        draw_polyline(cv, pts, 'snow:1')
    # 马车残骸
    wagon_wreck(cv, 128, 108)
    # 插在雪里的断枪、倒下的旗杆
    draw_polyline(cv, [(238, 108), (246, 82)], 'INK')
    draw_polyline(cv, [(239, 108), (247, 82)], 'wood:2')
    cv.dot(247, 81, 'iron:3')
    cv.dot(248, 80, 'iron:4')
    draw_polyline(cv, [(90, 116), (112, 111)], 'wood:1')
    fl = poly_mask([(90, 116), (84, 118), (88, 121), (82, 124), (92, 120)])
    cv.fill(fl, 'cloth_navy:2')
    # 雪松
    draw_pines(cv, [(270, 112, 46, 1), (298, 116, 60, 2), (318, 118, 44, 3), (80, 104, 24, 4), (254, 104, 22, 5), (218, 100, 14, 6), (98, 102, 16, 7)])
    # 前景雪堆
    drift = height_mask(152 + fbm1d(cv.w, 40, 11, 3) * 8)
    cv.ramp(drift, 0.5, rp('snow:0', 'snow:1', 'snow:2', 'snow:3'), soft=0.5)
    cv.fill(edge(drift, 0, -1), 'snow:4')
    # 风雪
    snowfall(cv, 520, 3, cols=('mist:5', 'snow:3', 'snow:4'), wind=2.0, streak=0.6, big=0.1)
    return cv


@scene('第四章：霜牙关要塞（雪山、城墙、旗帜、风雪）')
def bg_snow_fort():
    cv = Canvas()
    cv.light = vignette(cv, 0.12)
    sky = rp('mist:0', 'mist:1', 'mist:2', 'mist:3', 'mist:4', 'mist:5')
    cv.ramp(None, np.clip(vgrad(cv, -20, 100), 0, 1), sky, soft=0.6)
    # 远处大雪山
    snow_mountains(cv, [(40, 16, 60, 70), (122, 4, 70, 76), (208, 10, 80, 70), (296, 20, 70, 60)], 108, 8,
                   rp('mist:3', 'snow:1', 'snow:2', 'snow:3', 'snow:4'), rp('mist:1', 'mist:2', 'snow:0', 'snow:1'),
                   rp('stone:1', 'stone:2', 'stone:3'), rp('stone:0', 'stone:1', 'stone:2'), t=0.45, rock=0.05)
    # 两侧山肩（要塞卡在隘口）
    for (pts, ls, sd) in (([(-1, 34), (26, 44), (56, 66), (80, 88), (90, 122), (-1, 126)], True, 3),
                          ([(320, 40), (294, 50), (264, 70), (240, 90), (230, 122), (320, 126)], False, 4)):
        sh_m = poly_mask(pts)
        u = np.clip((cv.xx - (0 if ls else 230)) / 90.0, 0, 1)
        cv.fill(outline(sh_m) & (cv.yy < 120), 'stone:0')
        rock_face(cv, sh_m, sd, rp('stone:0', 'stone:1', 'stone:2', 'stone:3', 'stone:4'),
                  (0.6 - 0.3 * u) if ls else (0.25 + 0.1 * u), slope=0.5 if ls else -0.5,
                  snow=('snow:3', 'snow:4') if ls else ('snow:2', 'snow:3'))
        cv.fill(edge(sh_m, 0, -1), 'snow:4')
    stone = rp('INK', 'stone:1', 'stone:2', 'stone:3', 'stone:4', 'snow:2')
    # 城墙（砌块纹）
    wall = rect_mask(84, 76, 236, 120)
    for x in range(84, 236, 6):
        wall |= rect_mask(x, 72, x + 3, 76)
    u = np.clip((cv.xx - 84) / 152.0, 0, 1)
    bh_, bv_ = brick_lines(cv.xx, cv.yy - 76, 10, 5)
    cv.fill(outline(wall), 'INK')
    cv.ramp(wall, 0.58 - 0.25 * u - 0.1 * (bh_ | bv_), stone, soft=0.5)
    # 城墙两端的小角楼
    for (tx, tw) in [(80, 14), (226, 14)]:
        t_m = rect_mask(tx, 62, tx + tw, 120)
        for x in range(tx, tx + tw, 5):
            t_m |= rect_mask(x, 58, x + 2, 62)
        ut = np.clip((cv.xx - tx) / float(tw), 0, 1)
        cv.fill(outline(t_m), 'INK')
        cv.ramp(t_m, 0.62 - 0.4 * ut - 0.1 * (bh_ | bv_), stone, soft=0.5)
        cv.fill(rect_mask(tx + tw // 2 - 1, 68, tx + tw // 2, 72), 'INK')
        cv.fill(edge(t_m, 0, -1), 'snow:4')
    # 门楼双塔
    for (tx, tw) in [(120, 22), (178, 22)]:
        t_m = rect_mask(tx, 42, tx + tw, 120)
        for x in range(tx, tx + tw, 5):
            t_m |= rect_mask(x, 37, x + 2, 42)
        ut = np.clip((cv.xx - tx) / float(tw), 0, 1)
        bh2, bv2 = brick_lines(cv.xx - tx, cv.yy - 42, 8, 5)
        cv.fill(outline(t_m), 'INK')
        cv.ramp(t_m, 0.66 - 0.42 * ut - 0.1 * (bh2 | bv2), stone, soft=0.5)
        for wy in (52, 68):
            cv.fill(rect_mask(tx + tw // 2 - 1, wy, tx + tw // 2 + 1, wy + 4), 'fire:2')
            cv.fill(rect_mask(tx + tw // 2 - 1, wy, tx + tw // 2 + 1, wy), 'fire:3')
        cv.fill(edge(t_m, 0, -1), 'snow:4')
        cv.fill(shift(edge(t_m, 0, -1), 0, 1) & t_m & (cv.t4 > 0.5), 'snow:3')
    # 城门（放下的铁栅）
    gate = rect_mask(146, 86, 173, 120) | (ellipse_mask(159.5, 86, 13.5, 9) & (cv.yy <= 86))
    cv.fill(gate, 'INK')
    port = gate & (((cv.xx - 146) % 4 == 0) | ((cv.yy - 80) % 5 == 0)) & (cv.yy < 112)
    cv.fill(port, 'iron:2')
    cv.fill(port & ((cv.xx - 146) % 4 == 0) & (cv.yy % 5 == 1), 'iron:3')
    cv.fill(outline(gate) & wall, 'stone:4')
    cv.fill(edge(wall, 0, -1), 'snow:4')
    cv.fill(shift(edge(wall, 0, -1), 0, 1) & wall & (cv.t4 > 0.5), 'snow:3')
    # 城垛上的火把
    for fx in (100, 112, 208, 220):
        cv.fill(rect_mask(fx, 66, fx, 71), 'wood:1')
        cv.dot(fx, 65, 'fire:3')
        cv.dot(fx, 64, 'fire:4')
        cv.dot(fx + 1, 65, 'fire:2')
    # 塔顶白鹿旗（被风扯向右）
    for (fx, fy) in [(131, 37), (189, 37)]:
        cv.fill(rect_mask(fx, fy - 20, fx, fy), 'wood:1')
        cv.dot(fx, fy - 21, 'gold:3')
        fl = poly_mask([(fx + 1, fy - 20), (fx + 22, fy - 18), (fx + 18, fy - 14), (fx + 23, fy - 10), (fx + 1, fy - 10)])
        cv.fill(outline(fl) & (cv.xx > fx), 'INK')
        cv.ramp(fl, 0.72 - 0.42 * np.clip((cv.xx - fx) / 22.0, 0, 1), rp('cloth_navy:1', 'cloth_navy:2', 'cloth_navy:3', 'cloth_navy:4'), soft=0.5)
        stamp(cv, ['x.x', '.x.'], fx + 6, fy - 17, 'cloth_white:4')
        cv.fill(edge(fl, 0, -1) & (cv.xx < fx + 12), 'cloth_navy:4')
    # 城下雪原与道路
    ground = rect_mask(0, 120, 319, 179)
    cv.ramp(ground, 0.66 - 0.3 * np.clip(vgrad(cv, 120, 160), 0, 1), rp('snow:0', 'snow:1', 'snow:2', 'snow:3'), soft=0.5)
    road = poly_mask([(146, 120), (174, 120), (220, 180), (100, 180)])
    cv.ramp(road, 0.5 - 0.2 * np.clip(vgrad(cv, 120, 160), 0, 1), rp('snow:0', 'snow:1', 'snow:2'), soft=0.5)
    cv.fill(edge(ground, 0, -1) & ~road, 'snow:1')
    draw_pines(cv, [(20, 138, 52, 1), (44, 132, 36, 2), (300, 138, 54, 3), (276, 130, 34, 4), (70, 124, 20, 5), (252, 124, 18, 6)])
    snowfall(cv, 520, 9, cols=('mist:5', 'snow:3', 'snow:4'), wind=2.2, streak=0.6, big=0.1)
    return cv


# ===========================================================================
# 14. 决战前夜军营（营火、帐篷、星空、远方王城灯火）
# ===========================================================================
def sitter(cv, x, base, face, scale=1.0, lit='fire:1', lit2='fire:2'):
    """围坐在火边的人影：背光剪影，朝火一侧勾一道火光。face=1 面朝右。"""
    s = scale
    mm = Mask(cv.w, cv.h, 4)
    mm.poly([(x - 4 * s, base), (x - 3 * s, base - 7 * s), (x + 3 * s, base - 8 * s), (x + 4.5 * s, base)])
    mm.ellipse(x + 0.5 * s * face, base - 10.5 * s, 2.3 * s, 2.5 * s)
    mm.poly([(x + face * 2 * s, base - 5 * s), (x + face * 7 * s, base - 3 * s), (x + face * 7 * s, base - 1.5 * s), (x + face * 2 * s, base - 3 * s)])
    m = mm.get()
    cv.fill(m, 'INK')
    r = edge(m, face, 0)
    cv.fill(r, lit)
    cv.fill(r & (cv.yy < base - 8 * s), lit2)
    return m


@scene('第五章：决战前夜军营（营火、帐篷、星空、远方王城灯火）')
def bg_war_camp():
    cv = Canvas()
    fire = (160, 110)
    firelight = radial(cv, fire[0], fire[1], 130, 2.3) ** 2.2
    cv.light = vignette(cv, 0.14) + firelight * 0.6
    sky = rp('night:0', 'night:1', 'night:2', 'night:3', 'night:4', 'night:5')
    cv.ramp(None, np.clip(vgrad(cv, -10, 100), 0, 1) ** 1.2, sky, soft=0.55, gain=0.15)
    # 银河（斜向一条星带）
    band = np.exp(-(((cv.yy - 0.32 * cv.xx - 4) / 18.0) ** 2))
    n = fbm2d(cv.w, cv.h, 14, 10, 3, 3)
    cv.fill((band * 0.7 + n * 0.3 > 0.45 + cv.t4 * 0.35) & (cv.yy < 88), 'night:4')
    cv.fill((band * 0.7 + n * 0.3 > 0.62 + cv.t4 * 0.3) & (cv.yy < 88), 'night:5')
    stars(cv, cv.yy < 94, 170, 8, ymax=94, bias=1.2)
    stars(cv, (band > 0.5) & (cv.yy < 88), 80, 9, ymax=88, bias=1.0, twinkle=0.0)
    # 远山 + 地平线上的王城灯火
    far = height_mask(ridge_line(cv.w, 96, 6, 60, 13, 3))
    cv.ramp(far, 0.4, rp('INK', 'night:1', 'night:2', 'night:3'), soft=0.5, gain=0)
    halo = radial(cv, 240, 90, 44, 2.0)
    cv.fill((halo > 0.35 + cv.t4 * 0.4) & ~far & (cv.yy < 92), 'night:4')
    cs = royal_castle(240, 94, s=0.3)
    cv.fill(cs['mask'], 'night:1')
    cv.fill(rim_edges(cs['mask'])[0], 'night:3')
    lit_windows(cv, cs['windows'], cs['mask'], cols=('gold:3', 'gold:4'), seed=3, frac=0.7)
    city = rect_mask(214, 92, 266, 95)
    cv.fill(city, 'night:1')
    rng = np.random.default_rng(5)
    for _ in range(16):
        cv.dot(rng.uniform(214, 266), rng.uniform(92, 95), 'gold:3')
    # 营地草地（火光照到的地方转暖）
    ground = height_mask(98 + fbm1d(cv.w, 40, 2, 2) * 1.5)
    g = fbm2d(cv.w, cv.h, 3, 1.5, 4, 2)
    cv.ramp(ground, 0.1 + 0.05 * g, rp('INK', 'INK2', 'cloth_olive:0', 'leather:1', 'leather:2', 'leather:3', 'earth:3'), soft=0.5, gain=0.9)
    tuft = ground & (g > 0.35) & (cv.yy > 104)
    cv.fill(tuft & (firelight < 0.25), 'INK')
    cv.fill(tuft & (firelight >= 0.25) & (cv.t4 > 0.4), 'forest:1')
    # 帐篷
    canvas_r = rp('INK', 'INK2', 'cloth_brown:1', 'cloth_brown:2', 'cloth_brown:3', 'leather:3', 'earth:3', 'earth:4')
    for (cx, base, w, h, sd) in [(140, 98, 16, 11, 7), (184, 98, 16, 11, 8), (22, 104, 22, 18, 5), (300, 104, 22, 18, 6),
                                 (104, 104, 26, 20, 3), (216, 104, 26, 20, 4), (58, 118, 40, 32, 1), (262, 118, 40, 32, 2)]:
        tent(cv, cx, base, w, h, canvas_r, sd, t=0.22)
    # 军旗
    for (fx, fy, h) in [(84, 108, 46), (236, 108, 46)]:
        cv.fill(rect_mask(fx, fy - h, fx, fy), 'wood:1')
        cv.dot(fx, fy - h - 1, 'gold:3')
        fl = rect_mask(fx + 1, fy - h + 1, fx + 12, fy - h + 16) & ~(((cv.xx - fx) % 6 > 3) & (cv.yy > fy - h + 14))
        cv.fill(outline(fl) & (cv.xx > fx), 'INK')
        cv.ramp(fl, 0.5 - 0.35 * np.clip((cv.xx - fx) / 12.0, 0, 1), rp('cloth_navy:0', 'cloth_navy:1', 'cloth_navy:2', 'cloth_navy:3', 'cloth_navy:4'), soft=0.5)
        stamp(cv, ['x.x', '.x.', '.x.'], fx + 5, fy - h + 5, 'cloth_white:3')
    # 枪架
    for (sx, sy) in [(122, 108), (192, 108)]:
        for k in range(4):
            draw_polyline(cv, [(sx + k * 2, sy), (sx + k * 2 + 2, sy - 20)], 'wood:1')
            cv.dot(sx + k * 2 + 2, sy - 21, 'iron:3')
        cv.fill(rect_mask(sx - 1, sy - 8, sx + 9, sy - 8), 'wood:2')
    # 营火：石圈 + 柴堆 + 大火
    for k in range(9):
        a = math.pi * (k / 8.0)
        sx = fire[0] + math.cos(a) * 11
        sy = fire[1] + 3 + math.sin(a) * 2.5
        cv.fill(rect_mask(sx - 1, sy - 1, sx + 1, sy), 'stone:2')
        cv.dot(sx - 1, sy - 1, 'stone:4')
    draw_polyline(cv, [(fire[0] - 8, fire[1] + 2), (fire[0] + 6, fire[1] - 2)], 'wood:1')
    draw_polyline(cv, [(fire[0] + 8, fire[1] + 2), (fire[0] - 6, fire[1] - 2)], 'wood:0')
    flames(cv, fire[0] - 8, fire[0] + 8, fire[1], 14, 28, 5, density=2.4)
    embers(cv, 46, 6, (130, 44, 190, 100), big=0.1)
    # 围坐的人影 + 站岗的哨兵
    for (px_, py_, face, sc) in [(136, 116, 1, 1.0), (184, 116, -1, 1.0), (146, 122, 1, 1.15), (174, 122, -1, 1.15)]:
        sitter(cv, px_, py_, face, sc)
    m = Mask(cv.w, cv.h, 4)
    m.poly([(280, 118), (281, 102), (287, 102), (288, 118)])
    m.ellipse(284, 99, 2.5, 2.8)
    sen = m.get()
    cv.fill(sen, 'INK')
    cv.fill(edge(sen, -1, 0), 'fire:0')
    draw_polyline(cv, [(290, 118), (290, 86)], 'wood:1')
    cv.dot(290, 85, 'iron:3')
    cv.dot(290, 84, 'iron:4')
    return cv


# ===========================================================================
# 15. 黎明时的王城城门
# ===========================================================================
@scene('第五章：黎明时的王城城门（晨光、城墙、战旗）')
def bg_castle_gate():
    cv = Canvas()
    sun = (52, 96)
    cv.light = vignette(cv, 0.1)
    sky = rp('dawn:0', 'dawn:1', 'dawn:2', 'dawn:3', 'dawn:4', 'dawn:5', 'dawn:6', 'dawn:7', 'dawn:8')
    t = 0.6 * np.clip(vgrad(cv, -10, 110), 0, 1) ** 1.2 + 0.45 * radial(cv, sun[0], sun[1], 160, 1.5) ** 1.6
    cv.ramp(None, t, sky, soft=0.55)
    # 薄云（下缘受晨光）
    for (x0, x1, cy, th, sd) in [(150, 340, 26, 6, 3), (212, 330, 46, 5, 4), (-20, 96, 16, 6, 5), (-10, 70, 58, 3, 6), (84, 150, 40, 3, 7)]:
        streak_cloud(cv, x0, x1, cy, th, sd, rp('dawn:2', 'dawn:3', 'dawn:4', 'dawn:6', 'dawn:7'))
    stone = rp('INK', 'dawn:0', 'stone:1', 'stone:2', 'stone:3', 'dawn:6', 'dawn:7')
    roof = rp('INK', 'roof_blue:0', 'roof_blue:1', 'roof_blue:2', 'roof_blue:3', 'dawn:6')
    # 两侧城墙
    wall = rect_mask(-1, 70, 320, 124)
    for x in range(0, 320, 7):
        wall |= rect_mask(x, 65, x + 3, 70)
    cv.fill(outline(wall), 'INK')
    wbh, wbv = brick_lines(cv.xx, cv.yy - 70, 11, 6)
    cv.ramp(wall, 0.42 - 0.16 * np.clip(vgrad(cv, 70, 124), 0, 1) - 0.1 * (wbh | wbv), stone, soft=0.5)
    cv.fill(rim_edges(wall)[0], 'dawn:7')
    # 门楼：双圆塔 + 中央门墙
    parts = []
    for (tx, tw) in [(104, 30), (186, 30)]:
        body_m = rect_mask(tx, 40, tx + tw, 124)
        cone = poly_mask([(tx - 3, 41), (tx + tw / 2.0, 6), (tx + tw + 3, 41)])
        parts.append((body_m, cone, tx, tw))
    gatew = rect_mask(134, 50, 186, 124)
    for x in range(134, 186, 6):
        gatew |= rect_mask(x, 45, x + 3, 50)
    ug = np.clip((cv.xx - 134) / 52.0, 0, 1)
    cv.fill(outline(gatew), 'INK')
    gbh, gbv = brick_lines(cv.xx - 134, cv.yy - 50, 9, 6)
    cv.ramp(gatew, 0.48 - 0.1 * ug - 0.1 * np.clip(vgrad(cv, 50, 124), 0, 1) - 0.1 * (gbh | gbv), stone, soft=0.5)
    cv.fill(rim_edges(gatew)[0], 'dawn:7')
    for (body_m, cone, tx, tw) in parts:
        ut = np.clip((cv.xx - tx) / float(tw), 0, 1)
        cv.fill(outline(body_m | cone), 'INK')
        tbh, tbv = brick_lines(cv.xx - tx, cv.yy - 40, 8, 6)
        cv.ramp(body_m, 0.64 - 0.45 * ut - 0.12 * np.clip(vgrad(cv, 40, 124), 0, 1) - 0.1 * (tbh | tbv), stone, soft=0.5)
        uc = np.clip((cv.xx - tx + 3) / float(tw + 6), 0, 1)
        cv.ramp(cone, 0.55 + np.where(uc < 0.5, 0.15, -0.15), roof, soft=0.5)
        r1, r2 = rim_edges(body_m | cone)
        cv.fill(r1 | r2, 'dawn:8')
        for wy in (56, 76):
            cv.fill(rect_mask(tx + tw // 2 - 1, wy, tx + tw // 2 + 1, wy + 5), 'INK')
        cv.fill(rect_mask(tx + tw // 2, 5, tx + tw // 2, 7), 'INK')
    # 城门（紧闭，铁箍木门）
    gate = rect_mask(144, 84, 176, 124) | (ellipse_mask(160, 84, 16, 12) & (cv.yy <= 84))
    cv.fill(outline(gate), 'stone:4')
    cv.ramp(gate, 0.45 - 0.2 * np.clip((cv.xx - 144) / 32.0, 0, 1), rp('INK', 'wood:0', 'wood:1', 'wood:2'), soft=0.5)
    cv.fill(gate & ((cv.xx - 144) % 5 == 0), 'wood:0')
    cv.fill(gate & ((cv.yy == 92) | (cv.yy == 108)), 'iron:2')
    cv.fill(gate & (cv.xx == 160), 'INK')
    # 城上的黑鹰旗
    black = rp('cloth_black:0', 'cloth_black:1', 'cloth_black:2', 'cloth_black:3', 'cloth_black:4')
    for (bx, by) in [(113, 44), (195, 44), (150, 54)]:
        hang_banner(cv, bx, by, 13, 26, black, ['INK', 'cloth_crimson:2', 'cloth_crimson:3'], EAGLE, 'cloth_crimson:3', seed=bx)
    # 护城河与吊桥
    moat = rect_mask(0, 124, 319, 134)
    cv.ramp(moat, 0.5 + 0.1 * (cv.t4 > 0.7), rp('INK', 'dawn:1', 'dawn:2', 'dawn:4', 'dawn:6'), soft=0.5)
    cv.fill(rect_mask(144, 124, 176, 134), 'wood:1')
    cv.fill(rect_mask(144, 124, 176, 124), 'wood:3')
    # 晨雾
    fog = fbm2d(cv.w, cv.h, 60, 5, 21, 3)
    band = np.exp(-((cv.yy - 120) / 6.0) ** 2) * 0.6 + fog * 0.35
    cv.fill((band > cv.t4 * 0.8 + 0.2) & (np.abs(cv.yy - 120) < 10) & ~gate, 'dawn:5')
    # 我军战旗（近景，逆光）
    for (fx, h, lean) in [(40, 96, 1), (280, 96, -1)]:
        draw_polyline(cv, [(fx, 180), (fx + lean * 6, 180 - h)], 'INK')
        draw_polyline(cv, [(fx + 1, 180), (fx + 1 + lean * 6, 180 - h)], 'wood:1')
        top = 180 - h
        px0 = fx + lean * 6
        fl = poly_mask([(px0, top), (px0 + lean * 26, top + 3), (px0 + lean * 22, top + 9), (px0 + lean * 28, top + 16), (px0, top + 19)])
        cv.fill(outline(fl), 'INK')
        cv.ramp(fl, 0.6 - 0.35 * np.clip(np.abs(cv.xx - px0) / 26.0, 0, 1), rp('cloth_navy:0', 'cloth_navy:1', 'cloth_navy:2', 'cloth_navy:3', 'cloth_navy:4', 'dawn:7'), soft=0.5)
        stamp(cv, DEER, int(px0 + lean * 13 - 6), top + 4, 'cloth_white:3', mask=fl)
        cv.fill(rim_edges(fl)[0], 'dawn:8')
    cv.fill(rect_mask(0, 134, 319, 179), 'INK')
    cv.fill(height_mask(134 - np.abs(fbm1d(cv.w, 12, 2, 2)) * 5), 'INK')
    # 晨光中的飞鸟
    for (bx, by, fl) in [(70, 40, 0), (80, 36, 1), (92, 42, 0)]:
        bird(cv, bx, by, 'dawn:1', 1, fl)
    return cv


# ===========================================================================
# 16. 王都晨曦远景（重建中的城、飞鸟、朝阳）
# ===========================================================================
def hill_town(cv, top_fn, x0, x1, rows, seed, wall_r, roof_r, skip=None, row_gap=5.5, lit_x=None):
    """山坡上的城镇：沿山势一排排的小屋（墙 + 红屋顶），上排先画、下排压在前面。"""
    rng = np.random.default_rng(seed)
    for k in range(rows):
        x = x0 + rng.uniform(0, 4)
        while x < x1:
            w = rng.uniform(6, 10)
            y = top_fn(x + w / 2) + 7 + k * row_gap + rng.uniform(-1, 1)
            if skip and skip(x + w / 2, k):
                x += w * 0.8
                continue
            wall = rect_mask(x, y - 2, x + w - 1, y + 2)
            rh = w * rng.uniform(0.3, 0.42)
            roof = poly_mask([(x - 0.5, y - 1.5), (x + w / 2 - 0.5, y - 1.5 - rh), (x + w - 0.5, y - 1.5)])
            lit = cv.xx < x + w / 2
            cv.fill(wall & lit, wall_r[2])
            cv.fill(wall & ~lit, wall_r[1])
            cv.fill(wall & (cv.xx == int(x)), wall_r[-1])
            cv.fill(roof & lit, roof_r[2])
            cv.fill(roof & ~lit, roof_r[1])
            cv.fill(edge(roof, 0, -1) & lit, roof_r[-1])
            cv.fill(edge(wall, 0, 1), 'dawn:0')
            if rng.random() < 0.6:
                cv.dot(x + w * 0.65, y, 'dawn:0')
            x += w + rng.uniform(0.0, 2.0)


@scene('尾声：王都晨曦远景（重建中的城、飞鸟、朝阳）')
def bg_capital_dawn():
    cv = Canvas()
    sun = (112, 70)
    cv.light = vignette(cv, 0.08)
    sky = rp('dawn:1', 'dawn:2', 'dawn:3', 'dawn:4', 'dawn:5', 'dawn:6', 'dawn:7', 'dawn:8')
    t = 0.48 * np.clip(vgrad(cv, -10, 100), 0, 1) + 0.62 * radial(cv, sun[0], sun[1], 200, 1.4) ** 1.5
    cv.ramp(None, t, sky, soft=0.55)
    # 霞云
    for (x0, x1, cy, th, sd) in [(128, 340, 30, 7, 3), (176, 330, 52, 5, 4), (-20, 60, 20, 6, 5), (236, 330, 68, 3, 6), (96, 180, 12, 4, 7)]:
        streak_cloud(cv, x0, x1, cy, th, sd, rp('dawn:3', 'dawn:4', 'dawn:5', 'dawn:7', 'dawn:8'))
    # 太阳
    sd_ = ellipse_mask(sun[0], sun[1], 12, 12)
    cv.fill(dilate(sd_, 2) & ~sd_ & (cv.t4 > 0.5), 'dawn:8')
    cv.fill(sd_, 'dawn:8')
    # 远山
    far = height_mask(ridge_line(cv.w, 100, 9, 70, 4, 3))
    cv.ramp(far, 0.42 + 0.3 * radial(cv, sun[0], sun[1], 160, 1.4), rp('dawn:2', 'dawn:3', 'dawn:4', 'dawn:5', 'dawn:6'), soft=0.5)
    # 王城之丘
    xs = np.arange(cv.w, dtype=float)
    top_arr = 114 - 36 * np.exp(-((xs - 188) / 64.0) ** 2) + fbm1d(cv.w, 12, 5, 2) * 1.2

    def top_fn(x):
        return float(top_arr[int(min(cv.w - 1, max(0, x)))])
    hill = height_mask(top_arr)
    lit_side = cv.xx < 188
    cv.ramp(hill, 0.3 + 0.18 * lit_side - 0.15 * np.clip(vgrad(cv, 80, 130), 0, 1), rp('dawn:0', 'dawn:1', 'dawn:2', 'forest:2', 'dawn:4', 'dawn:5'), soft=0.5)
    cv.fill(edge(hill, 0, -1) & lit_side, 'dawn:6')
    # 城镇（主堡所在的山顶留空）
    def skip(x, k):
        return k < 2 and 152 < x < 224
    hill_town(cv, top_fn, 116, 268, 4, 12, rp('dawn:0', 'dawn:2', 'earth:2', 'dawn:6'), rp('dawn:0', 'roof_red:1', 'roof_red:2', 'dawn:6'), skip=skip, row_gap=7)
    # 王城（主塔一侧搭着脚手架）
    base = int(top_fn(188) + 9)
    cs = royal_castle(188, base, s=0.5)
    draw_castle(cv, cs, body=rp('dawn:0', 'dawn:1', 'stone:2', 'stone:3', 'dawn:6', 'dawn:7'),
                roof=rp('dawn:0', 'roof_blue:0', 'roof_blue:1', 'roof_blue:2', 'roof_blue:3', 'dawn:6'),
                t_body=0.5, t_roof=0.52, rim='dawn:8', rim2='dawn:7')
    lit_windows(cv, cs['windows'], cs['mask'], cols=('dawn:1', 'dawn:1'), seed=2, frac=1.0)
    for (tx, ty) in cs['tips']:
        flag(cv, tx, ty, 'cloth_white:4', 'cloth_sky:3', length=4, height=2, pole='dawn:1', pole_h=3)
    scaf = np.zeros((cv.h, cv.w), bool)
    for (sx0, sx1, sy0, sy1) in [(193, 203, base - 64, base - 38), (204, 214, base - 44, base - 16)]:
        for x in range(sx0, sx1 + 1, 4):
            scaf |= rect_mask(x, sy0, x, sy1)
        for y in range(sy0, sy1 + 1, 5):
            scaf |= rect_mask(sx0, y, sx1, y)
    cv.fill(scaf, 'wood:1')
    cv.fill(scaf & (cv.t4 > 0.5), 'wood:3')
    draw_polyline(cv, [(214, base - 44), (230, base - 58)], 'wood:1')
    draw_polyline(cv, [(230, base - 58), (230, base - 48)], 'leather:3')
    cv.fill(rect_mask(229, base - 48, 231, base - 46), 'stone:3')
    # 城墙（沿山腰）
    wall = np.zeros((cv.h, cv.w), bool)
    for x in range(110, 272):
        y = int(top_fn(x) + 36)
        if y > 124:
            continue
        wall[y - 5:y + 1, x] = True
        if (x // 3) % 2 == 0:
            wall[y - 7:y - 5, x] = True
    for tx in (114, 188, 264):
        y = int(top_fn(tx) + 36)
        wall |= rect_mask(tx - 4, y - 11, tx + 4, y + 1)
    cv.fill(outline(wall), 'dawn:0')
    cv.ramp(wall, 0.55 - 0.25 * np.clip((cv.xx - 110) / 160.0, 0, 1), rp('dawn:0', 'dawn:1', 'stone:2', 'stone:3', 'dawn:6', 'dawn:7'), soft=0.5)
    cv.fill(rim_edges(wall)[0], 'dawn:8')
    # 谷底晨雾 + 河
    fog = fbm2d(cv.w, cv.h, 70, 5, 31, 3)
    for (cy, amp, col) in [(118, 0.6, 'dawn:6'), (126, 0.5, 'dawn:5')]:
        band = np.exp(-((cv.yy - cy) / 6.0) ** 2) * amp + fog * 0.35
        cv.fill((band > cv.t4 * 0.8 + 0.15) & (np.abs(cv.yy - cy) < 10), col)
    river = poly_mask([(-1, 130), (120, 126), (320, 129), (320, 134), (-1, 137)])
    cv.ramp(river, 0.55, rp('dawn:3', 'dawn:5', 'dawn:7', 'dawn:8'), soft=0.5)
    cv.fill(river & (cv.t4 > 0.8) & (np.abs(cv.xx - sun[0]) < 26), 'dawn:8')
    # 河这边的田垄（晨光斜照，一条条亮暗相间）
    fields = rect_mask(0, 137, 319, 179) & ~river
    strip = ((cv.xx * 0.35 + cv.yy * 1.0 + fbm2d(cv.w, cv.h, 30, 8, 44, 2) * 6) % 9) < 4.5
    cv.ramp(fields, 0.42 - 0.3 * np.clip(vgrad(cv, 137, 170), 0, 1) + 0.1 * strip, rp('dawn:0', 'dawn:1', 'forest:1', 'dawn:3', 'cloth_olive:3', 'dawn:5'), soft=0.5)
    road = poly_mask([(150, 180), (170, 180), (190, 140), (184, 137)])
    cv.fill(road, 'dawn:4')
    # 近景山坡剪影 + 树
    fgm = height_mask(152 + fbm1d(cv.w, 30, 8, 3) * 5)
    cv.fill(fgm, 'dawn:0')
    cv.fill(edge(fgm, 0, -1), 'dawn:3')
    trees = np.zeros((cv.h, cv.w), bool)
    for (tx, th, sd2) in [(16, 34, 1), (38, 24, 2), (300, 36, 3), (276, 24, 4)]:
        trees = round_tree(trees, tx, 156, th, sd2)
    cv.fill(trees, 'dawn:0')
    cv.fill((edge(trees, -1, 0) | edge(trees, 0, -1)) & (cv.xx < 160), 'dawn:3')
    # 飞鸟（人字形，飞向朝阳）
    for (bx, by, sz, fl) in [(150, 26, 2, 0), (160, 32, 2, 1), (140, 32, 1, 0), (170, 38, 1, 1), (130, 38, 1, 1), (180, 44, 1, 0), (120, 44, 1, 0), (206, 20, 1, 1)]:
        bird(cv, bx, by, 'dawn:1', sz, fl)
    return cv


# ===========================================================================
# Logo：「灰烬王冠」手工笔画字形（不用现成字体）
# ===========================================================================
class Glyph:
    """用笔画拼字：横（带宋体三角笔锋）、竖、撇（渐细弧线）、捺（渐粗带平脚）、点（水滴）。
    所有笔画都是多边形，4 倍超采样后二值化，得到干净的 1 倍像素边缘。"""

    def __init__(self, w, h, ox=0, oy=0, ss=4, sx=1.0, sy=1.0):
        self.m = Mask(w, h, ss)
        self.ox, self.oy, self.sx, self.sy = ox, oy, sx, sy

    def _p(self, x, y):
        return (self.ox + x * self.sx, self.oy + y * self.sy)

    def poly(self, pts):
        self.m.poly([self._p(x, y) for x, y in pts])

    def H(self, x0, x1, y, t=4.0, serif=True):
        """横：矩形 + 右端宋体三角笔锋。"""
        a, b = y - t / 2.0, y + t / 2.0
        self.poly([(x0, a + 0.4), (x0 + 1, a), (x1, a), (x1, b), (x0, b)])
        if serif:
            self.poly([(x1 - t * 1.4, a), (x1 - t * 0.35, a - t * 0.85), (x1 + 1.0, a + t * 0.25), (x1 + 1.0, b - 0.3), (x1 - 0.5, b), (x1 - t * 1.4, b)])

    def V(self, x, y0, y1, t=5.0, hook=0.0, cap=True):
        """竖：顶端斜切起笔；hook>0 时底部向左上出钩。"""
        l, r = x - t / 2.0, x + t / 2.0
        top = [(l, y0 + (1.2 if cap else 0)), (r - 0.6, y0 - (0.8 if cap else 0)), (r, y0 + 0.4)]
        if hook:
            self.poly(top + [(r, y1), (l - hook, y1 - hook * 0.9), (l, y1 - t * 0.6)])
            self.poly([(l, y1 - t * 0.9), (r, y1 - t * 0.5), (r, y1), (l - hook, y1 - hook * 0.95)])
        else:
            self.poly(top + [(r, y1), (l, y1)])

    def curve(self, p0, c, p1, w0, w1, n=14, foot=0.0):
        """二次贝塞尔中线 + 逐点宽度的笔画；foot>0 时末端补一个向右的平脚（捺）。"""
        pts = []
        for i in range(n + 1):
            t = i / float(n)
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1]
            pts.append((x, y))
        ws = [w0 + (w1 - w0) * (i / float(n)) for i in range(n + 1)]
        left, right = [], []
        for i, (x, y) in enumerate(pts):
            if i == 0:
                dx, dy = pts[1][0] - x, pts[1][1] - y
            elif i == n:
                dx, dy = x - pts[i - 1][0], y - pts[i - 1][1]
            else:
                dx, dy = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
            L = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / L, dx / L
            w = ws[i] / 2.0
            left.append((x + nx * w, y + ny * w))
            right.append((x - nx * w, y - ny * w))
        self.poly(left + right[::-1])
        if foot:
            x, y = pts[-1]
            self.poly([(x - w1 * 0.6, y - w1 * 0.5), (x + foot, y + w1 * 0.15), (x + foot * 0.6, y + w1 * 0.55), (x - w1 * 0.5, y + w1 * 0.5)])

    def P(self, p0, c, p1, w0=5.0, w1=1.2):
        """撇：起笔粗、收笔尖。"""
        self.curve(p0, c, p1, w0, w1)

    def N(self, p0, c, p1, w0=1.6, w1=5.5, foot=3.0):
        """捺：起笔细、收笔粗，末端平脚。"""
        self.curve(p0, c, p1, w0, w1, foot=foot)

    def D(self, x0, y0, x1, y1, w=4.0):
        """点：细头粗尾的水滴。"""
        self.curve((x0, y0), ((x0 + x1) / 2.0, (y0 + y1) / 2.0), (x1, y1), w * 0.45, w)
        self.m.ellipse(self.ox + x1 * self.sx, self.oy + y1 * self.sy, w * 0.5 * self.sx, w * 0.45 * self.sy)

    def get(self):
        return self.m.get()


# 各字设计框内的笔画（宽度按字形繁简分配：灰 42、烬 46、王 38、冠 44；高 40）
def glyph_hui(g):          # 灰
    g.H(3, 39, 6, 3.8)
    g.P((14, 6.5), (14, 29), (1.5, 39.5), 5.8, 1.2)
    g.D(20.5, 16, 23.5, 24, 4.6)
    g.P((38, 14), (37, 19), (33, 24), 4.8, 2.0)
    g.P((29.5, 11), (29.5, 30), (16, 40), 5.6, 1.2)
    g.N((29.5, 25), (33.5, 33), (40.5, 38), 1.8, 6.0, foot=3.0)


def glyph_jin(g):          # 烬
    # 火字旁
    g.D(2.2, 12, 4.4, 19.5, 4.2)
    g.P((16.5, 10), (16, 14), (13, 18.5), 4.2, 1.8)
    g.P((10, 1.5), (10, 29), (2.5, 39.5), 5.4, 1.2)
    g.D(12.5, 24, 16, 30.5, 4.2)
    # 尽
    g.H(21, 40.5, 5, 3.8, serif=False)
    g.V(41, 3.4, 15.5, 4.6, cap=False)
    g.H(24, 40, 14.5, 3.6, serif=False)
    g.P((23.5, 4), (24, 22), (17.5, 32.5), 5.2, 1.2)
    g.N((26.5, 16.5), (33, 24), (45.5, 28.5), 1.8, 5.6, foot=2.4)
    g.D(25, 27, 28.5, 31, 4.2)
    g.D(30.5, 33, 36, 38.5, 4.8)


def glyph_wang(g):         # 王
    g.H(5, 33, 6.5, 4.4)
    g.H(8, 30, 20.5, 4.2)
    g.H(2, 36, 35, 5.2)
    g.V(19, 6.5, 35, 5.8, cap=False)


def glyph_guan(g):         # 冠
    # 冖
    g.V(5, 4, 12.5, 4.6)
    g.H(5, 38.5, 6, 3.8, serif=False)
    g.P((39.5, 4.3), (40, 8.5), (36.5, 12.5), 4.8, 2.0)
    # 元
    g.H(8, 19, 17, 3.4, serif=False)
    g.H(3, 22, 24, 3.8, serif=False)
    g.P((10.5, 25), (10.5, 33.5), (2.5, 39.5), 4.8, 1.2)
    g.V(16.5, 25, 36, 4.4, cap=False)
    g.curve((16.5, 34.5), (17, 38), (23.5, 38), 4.4, 3.4)
    g.poly([(21.5, 39.8), (25, 39.8), (25, 32.5), (22.2, 35.8)])
    # 寸
    g.H(25.5, 43, 23, 3.8)
    g.V(36.5, 15, 37, 5.0, hook=4.6)
    g.D(28.5, 27, 31.5, 32.5, 4.4)


GLYPH_W = [42, 46, 38, 44]
GLYPHS = [glyph_hui, glyph_jin, glyph_wang, glyph_guan]

# 5×7 像素大写字母（副标题 THE ASHEN CROWN 用，手工逐点绘制）
MINI = {
    'T': ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '..#..'],
    'H': ['#...#', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
    'E': ['#####', '#....', '#....', '####.', '#....', '#....', '#####'],
    'A': ['..#..', '.#.#.', '#...#', '#...#', '#####', '#...#', '#...#'],
    'S': ['.####', '#....', '#....', '.###.', '....#', '....#', '####.'],
    'N': ['#...#', '##..#', '#.#.#', '#.#.#', '#..##', '#...#', '#...#'],
    'C': ['.###.', '#...#', '#....', '#....', '#....', '#...#', '.###.'],
    'R': ['####.', '#...#', '#...#', '####.', '#.#..', '#..#.', '#...#'],
    'O': ['.###.', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
    'W': ['#...#', '#...#', '#...#', '#.#.#', '#.#.#', '##.##', '#...#'],
    ' ': ['..', '..', '..', '..', '..', '..', '..'],
}


def text_mask(w, h, s, x, y, gap=2):
    m = np.zeros((h, w), bool)
    cx = x
    for ch in s:
        bmp = MINI[ch]
        for j, row in enumerate(bmp):
            for i, c in enumerate(row):
                if c == '#':
                    m[y + j, cx + i] = True
        cx += len(bmp[0]) + gap
    return m


def text_width(s, gap=2):
    return sum(len(MINI[c][0]) + gap for c in s) - gap


def crown_mask(w, h, cx, top, width=30, height=14, ss=8, orb=1.6):
    """王冠：弧形底带 + 五个尖（中间最高）+ 尖端圆珠。返回 (整体遮罩, 底带遮罩, 各尖端坐标)。"""
    mm = Mask(w, h, ss)
    x0, x1 = cx - width / 2.0, cx + width / 2.0
    base = top + height
    band_t = base - height * 0.34
    tip_top = top + orb * 2.0
    tips = [(x0 - 0.3, tip_top + height * 0.3), (x0 + width * 0.25, tip_top + height * 0.12), (cx, tip_top),
            (x1 - width * 0.25, tip_top + height * 0.12), (x1 + 0.3, tip_top + height * 0.3)]
    valleys = [(x0 + width * 0.125, band_t - height * 0.05), (x0 + width * 0.375, band_t - height * 0.1),
               (x1 - width * 0.375, band_t - height * 0.1), (x1 - width * 0.125, band_t - height * 0.05)]
    pts = [(x0, base - 0.8), (x0, band_t)]
    for i, tp in enumerate(tips):
        pts.append(tp)
        if i < len(valleys):
            pts.append(valleys[i])
    pts += [(x1, band_t), (x1, base - 0.8), (cx, base + 0.6)]
    mm.poly(pts)
    for (tx, ty) in tips:
        mm.ellipse(tx, ty - orb * 0.8, orb, orb)
    band = Mask(w, h, ss)
    band.poly([(x0, base - 0.8), (x0, band_t), (x1, band_t), (x1, base - 0.8), (cx, base + 0.6)])
    return mm.get(), band.get(), [(int(round(tx)), int(round(ty - orb * 0.8))) for tx, ty in tips]


def metal(img, m, top, bottom, seed=0, outline_col='INK', shadow=True, diag=True):
    """把遮罩渲染成「金→余烬橙」的金属字：竖直抖动渐变 + 斜面（上左亮、下右暗）+ 1px INK 外描边 + 右下投影。"""
    h, w = m.shape
    yy, xx = np.mgrid[0:h, 0:w]
    t4 = B4[yy % 4, xx % 4]
    px = img
    ol = outline(m, diag=diag)
    if shadow:
        body = m | ol
        sh1 = shift(body, 1, 1) & ~body
        sh2 = shift(body, 2, 2) & ~body & ~sh1
        px[sh2 & (px[..., 3] == 0)] = C('INK2') + (255,)
        px[sh1 & (px[..., 3] == 0)] = C('fire:0') + (255,)
    px[ol] = C(outline_col) + (255,)
    ramp_cols = np.array([C(c) for c in ['fire:1', 'fire:2', 'gold:3', 'fire:3', 'gold:4', 'fire:4']], np.uint8)
    tt = 1 - np.clip((yy - top) / float(bottom - top), 0, 1)
    tt = tt ** 0.85
    idx = ramp_idx(tt, len(ramp_cols), t4, 0.55)
    col = ramp_cols[idx]
    px[m, :3] = col[m]
    px[m, 3] = 255
    top_e = edge(m, 0, -1)
    left_e = edge(m, -1, 0) & ~top_e
    bot_e = edge(m, 0, 1) & ~top_e
    right_e = edge(m, 1, 0) & ~bot_e & ~top_e
    px[top_e] = C('fire:4') + (255,)
    px[left_e & (tt > 0.4)] = C('gold:4') + (255,)
    px[left_e & (tt <= 0.4)] = C('fire:3') + (255,)
    px[right_e & (tt > 0.55)] = C('gold:2') + (255,)
    px[right_e & (tt <= 0.55)] = C('fire:1') + (255,)
    px[bot_e] = C('fire:0') + (255,)
    return px


def diamond(m, x, y, r):
    for dy in range(-r, r + 1):
        for dx in range(-(r - abs(dy)), r - abs(dy) + 1):
            if 0 <= y + dy < m.shape[0] and 0 <= x + dx < m.shape[1]:
                m[y + dy, x + dx] = True


def make_logo():
    W_, H_ = 230, 64
    img = np.zeros((H_, W_, 4), np.uint8)
    # 四个字
    gm = np.zeros((H_, W_), bool)
    gap = 6
    total = sum(GLYPH_W) + gap * (len(GLYPH_W) - 1)
    x = (W_ - total) // 2
    gy0 = 13
    for fn, gw in zip(GLYPHS, GLYPH_W):
        g = Glyph(W_, H_, ox=x, oy=gy0)
        fn(g)
        gm |= g.get()
        x += gw + gap
    gm = clean(gm)
    metal(img, gm, gy0 + 2, gy0 + 40)
    # 王冠纹饰（居中）+ 两侧金线（菱形节点）
    cx = W_ // 2
    cm, band, tips = crown_mask(W_, H_, cx, 0, width=30, height=12, orb=1.5)
    orn = np.zeros((H_, W_), bool)
    for (a, b) in [(cx - 80, cx - 17), (cx + 17, cx + 80)]:
        orn[7, a:b] = True
    for dx in (-80, 79):
        diamond(orn, cx + dx, 7, 2)
    for dx in (-60, -40, 40, 60):
        diamond(orn, cx + dx, 7, 1)
    for dx in (-22, 21):
        diamond(orn, cx + dx, 7, 1)
    tmp = np.zeros_like(img)
    ol = outline(orn, diag=True) & ~dilate(cm, 1)
    img[ol & (img[..., 3] == 0)] = C('INK') + (255,)
    img[orn] = C('gold:3') + (255,)
    img[orn & edge(orn, 0, -1)] = C('gold:4') + (255,)
    metal(img, cm, 0, 12, shadow=True)
    bys, bxs = np.nonzero(band)
    by = int(round(bys.mean()))
    for dx, col, hi in [(0, 'hair_red:3', 'hair_red:4'), (-8, 'cloth_sky:3', 'cloth_white:4'), (8, 'cloth_sky:3', 'cloth_white:4')]:
        img[by, cx + dx - 1] = C(col) + (255,)
        img[by, cx + dx] = C(col) + (255,)
        img[by - 1, cx + dx - 1] = C(hi) + (255,)
        img[by - 1, cx + dx] = C(col) + (255,)
    for (tx, ty) in tips:
        if 0 <= ty < H_:
            img[ty, tx] = C('fire:4') + (255,)
    # 飘起的余烬（点缀在「灰烬」上方）
    for (x_, y_, c) in [(30, 11, 'fire:3'), (48, 8, 'fire:2'), (60, 12, 'fire:4'), (74, 5, 'fire:3'), (88, 10, 'fire:2'), (22, 4, 'fire:2')]:
        if img[y_, x_, 3] == 0:
            img[y_, x_] = C(c) + (255,)
    # 副标题
    s_ = 'THE ASHEN CROWN'
    tw = text_width(s_)
    tx = (W_ - tw) // 2
    tm = text_mask(W_, H_, s_, tx, 56)
    to = outline(tm, diag=True)
    img[to] = C('INK') + (255,)
    img[tm] = C('gold:3') + (255,)
    yy = np.mgrid[0:H_, 0:W_][0]
    img[tm & (yy <= 57)] = C('gold:4') + (255,)
    img[tm & (yy >= 61)] = C('fire:2') + (255,)
    for (a, b) in [(tx - 30, tx - 6), (tx + tw + 6, tx + tw + 30)]:
        seg = np.zeros((H_, W_), bool)
        seg[59, a:b] = True
        diamond(seg, a if a < tx else b, 59, 1)
        img[outline(seg, diag=True) & (img[..., 3] == 0)] = C('INK') + (255,)
        img[seg] = C('gold:2') + (255,)
    return Image.fromarray(img, 'RGBA')


def make_icon():
    """32×32 王冠图标（favicon）：深色圆角底 + 暖光 + 金冠 + 宝石 + 余烬。"""
    S = 32
    img = np.zeros((S, S, 4), np.uint8)
    yy, xx = np.mgrid[0:S, 0:S]
    plate = Mask(S, S, 4)
    plate.poly([(3, 1), (28, 1), (30, 3), (30, 28), (28, 30), (3, 30), (1, 28), (1, 3)])
    pm = plate.get()
    ramp_cols = np.array([C(c) for c in ['night:0', 'night:1', 'dusk:1', 'dusk:2', 'dusk:3', 'dusk:4']], np.uint8)
    t4 = B4[yy % 4, xx % 4]
    glow = np.clip(1 - np.sqrt(((xx - 15.5) / 15.0) ** 2 + ((yy - 18) / 11.0) ** 2), 0, 1)
    tt = np.clip((yy - 2) / 34.0, 0, 1) * 0.6 + glow * 0.55
    idx = ramp_idx(tt, len(ramp_cols), t4, 0.6)
    img[pm, :3] = ramp_cols[idx][pm]
    img[pm, 3] = 255
    rimm = pm & ~erode(pm, 1)
    img[rimm, :3] = C('INK')
    img[pm & edge(erode(pm, 1), 0, -1) & ~rimm, :3] = C('dusk:2')
    cm, band, tips = crown_mask(S, S, 15.5, 6, width=22, height=15, orb=1.7)
    tmp = np.zeros((S, S, 4), np.uint8)
    metal(tmp, cm, 6, 21, shadow=True)
    sel = tmp[..., 3] > 0
    img[sel] = tmp[sel]
    bys, bxs = np.nonzero(band)
    by = int(round(bys.mean()))
    img[by, 15] = C('hair_red:3') + (255,)
    img[by, 16] = C('hair_red:3') + (255,)
    img[by - 1, 15] = C('hair_red:4') + (255,)
    img[by - 1, 16] = C('hair_red:3') + (255,)
    for x_ in (9, 22):
        img[by, x_] = C('cloth_sky:3') + (255,)
        img[by - 1, x_] = C('cloth_white:4') + (255,)
    for (tx, ty) in tips:
        img[ty, tx] = C('fire:4') + (255,)
    for (x, y, c) in [(5, 26, 'fire:3'), (8, 28, 'fire:2'), (25, 27, 'fire:3'), (23, 25, 'fire:2'), (27, 23, 'fire:1'), (4, 23, 'fire:1')]:
        img[y, x] = C(c) + (255,)
    return Image.fromarray(img, 'RGBA')


# ===========================================================================
# 标题画面背景 + 余烬粒子精灵表
# ===========================================================================
def dead_tree(cv, x, base, h, side, seed):
    """枯树剪影：弯曲主干 + 分叉细枝。side=1 向右伸展。"""
    rng = np.random.default_rng(seed)
    mm = Mask(cv.w, cv.h, 4)

    def branch(x0, y0, ang, L, th, depth):
        x1 = x0 + math.cos(ang) * L
        y1 = y0 - math.sin(ang) * L
        nx, ny = math.sin(ang) * th / 2, math.cos(ang) * th / 2
        mm.poly([(x0 - nx, y0 - ny), (x1, y1), (x0 + nx, y0 + ny)])
        if depth > 0:
            for k in range(2):
                a2 = ang + rng.uniform(0.3, 0.8) * (1 if k else -1) * (0.8 if side > 0 else 1)
                branch(x0 + (x1 - x0) * rng.uniform(0.5, 0.85), y0 + (y1 - y0) * rng.uniform(0.5, 0.85), a2, L * rng.uniform(0.45, 0.65), th * 0.55, depth - 1)
    branch(x, base, math.pi / 2 - side * 0.25, h, h * 0.16, 3)
    return mm.get()


TITLE_LOGO_Y = 14      # 标题画面里 Logo 的建议 y（x 居中）；菜单建议放在 y≈110~175


def make_title_bg():
    cv = Canvas()
    glow = radial(cv, 160, 150, 200, aspect=1.6)
    cv.light = vignette(cv, 0.16)
    sky = rp('night:0', 'night:1', 'night:2', 'dusk:1', 'dusk:2', 'dusk:3', 'dusk:4', 'dusk:5', 'dusk:6')
    t = 0.22 * np.clip(vgrad(cv, 0, 150), 0, 1) + 0.8 * glow ** 1.7
    cv.ramp(None, t, sky, soft=0.65)
    stars(cv, t < 0.3, 90, 17, ymax=80, bias=1.4)
    # 弯月（左上）
    moon(cv, 36, 26, 9, colors=('dawn:8', 'dawn:7', 'dawn:6'), phase=0.55)
    # 远山
    far = height_mask(ridge_line(cv.w, 132, 10, 60, 7, 3))
    cv.ramp(far, 0.2 + 0.4 * glow, rp('INK', 'night:1', 'dusk:1', 'dusk:2', 'dusk:3'), soft=0.5)
    cv.fill(edge(far, 0, -1) & (glow > 0.55), 'dusk:4')
    # 王城上空翻涌的烟（底部被火光映红）
    smoke_plumes(cv, [(160, 110, 110, 14, 80, 0.7), (132, 118, 80, 8, 40, 0.9), (190, 118, 70, 8, 36, 1.1)],
                 rp('smoke:0', 'smoke:1', 'smoke:2', 'smoke:3', 'roof_red:1', 'dusk:4', 'dusk:5'), seed=31, thr=0.5)
    # 城堡所在山丘 + 两侧崖壁
    xs = np.arange(cv.w)
    hill_top = 156 - 8 * np.exp(-((xs - 160) / 60.0) ** 2) + fbm1d(cv.w, 10, 5, 2) * 1.5
    cliffs = 160 - np.clip(np.abs(xs - 160) - 96, 0, None) * 0.55 + fbm1d(cv.w, 6, 8, 3) * 2.5
    hill = height_mask(np.minimum(hill_top, cliffs))
    cv.fill(hill, 'INK')
    cv.fill(edge(hill, 0, -1) & (glow > 0.3), 'dusk:2')
    cv.fill(edge(hill, 0, -1) & (glow > 0.62), 'fire:1')
    # 燃烧的白鹿城
    cs = royal_castle(160, 152, s=0.6)
    draw_castle(cv, cs, body=rp('INK', 'INK2', 'dusk:0', 'dusk:1', 'dusk:2'), roof=rp('INK', 'INK2', 'dusk:0', 'dusk:1'),
                t_body=0.2 + 0.25 * np.clip(vgrad(cv, 80, 150), 0, 1), t_roof=0.25, rim='fire:1', rim2=None, mode='top')
    cv.fill(rim_edges(cs['mask'], 'top')[0] & (cv.t4 > 0.5), 'fire:2')
    lit_windows(cv, cs['windows'], cs['mask'], cols=('fire:2', 'fire:3'), seed=4, frac=0.9)
    gx0, gy0, gx1, gy1 = cs['gate']
    cv.fill(rect_mask(gx0, gy0 + 2, gx1, gy1), 'fire:2')
    cv.fill(rect_mask(gx0 + 1, gy0 + 4, gx1 - 1, gy1), 'fire:3')
    for (fx, fy, fw, fh, sd) in [(143, 116, 6, 9, 1), (182, 118, 5, 8, 2), (160, 104, 4, 7, 3), (118, 128, 6, 7, 4), (204, 130, 6, 7, 5)]:
        flames(cv, fx - fw / 2.0, fx + fw / 2.0, fy, fh * 0.5, fh, sd, density=2.0)
    flames(cv, 100, 220, 153, 3, 8, 6, density=1.2)
    # 左：枯树；右：折断的旗杆与烧破的白鹿旗
    tree = dead_tree(cv, 20, 150, 58, 1, 3)
    cv.fill(tree, 'INK')
    cv.fill(edge(tree, 1, 0) & (cv.t4 > 0.3), 'dusk:1')
    draw_polyline(cv, [(292, 160), (288, 96)], 'INK')
    draw_polyline(cv, [(293, 160), (289, 96)], 'INK')
    flag_m = poly_mask([(289, 97), (270, 100), (274, 106), (268, 112), (276, 116), (288, 113)])
    holes = ellipse_mask(278, 108, 3, 2) | ellipse_mask(271, 101, 1.5, 1.5)
    flag_m &= ~holes
    cv.fill(outline(flag_m), 'INK')
    cv.ramp(flag_m, 0.45 - 0.3 * np.clip((289 - cv.xx) / 20.0, 0, 1), rp('INK', 'cloth_navy:0', 'cloth_navy:1', 'cloth_navy:2'), soft=0.5)
    cv.fill(outline(holes) & flag_m & (cv.t4 > 0.3), 'fire:1')
    stamp(cv, ['x.x', '.x.'], 280, 103, 'cloth_white:1')
    # 静态余烬（运行时再叠加 title_embers 动画粒子）
    embers(cv, 70, 23, (40, 40, 280, 150), big=0.12, wind=0.3)
    embers(cv, 30, 24, (110, 70, 210, 150), big=0.2)
    return cv


def make_title_embers():
    """余烬粒子精灵表：4 种（大 / 中 / 小 / 火花）× 4 帧闪烁，每格 8×8，锚点在中心。
    大余烬带半透明光晕（特效允许半透明），其余均为不透明像素。"""
    cell = 8
    kinds = ['ember_big', 'ember_mid', 'ember_small', 'spark']
    img = np.zeros((cell * len(kinds), cell * 4, 4), np.uint8)
    frames, anims = {}, {}

    def put(ix, iy, x, y, col, a=255):
        px = img[iy * cell + y, ix * cell + x]
        px[:3] = C(col)
        px[3] = a

    for f in range(4):
        # 大：十字核心 + 光晕
        core = ['fire:4', 'fire:3', 'fire:4', 'fire:3'][f]
        arm = ['fire:3', 'fire:2', 'fire:2', 'fire:2'][f]
        halo_a = [120, 80, 100, 60][f]
        for (x, y) in [(3, 3), (4, 3), (3, 4), (4, 4)]:
            put(f, 0, x, y, core)
        for (x, y) in [(3, 2), (4, 2), (2, 3), (2, 4), (5, 3), (5, 4), (3, 5), (4, 5)]:
            put(f, 0, x, y, arm)
        for (x, y) in [(2, 2), (5, 2), (2, 5), (5, 5), (3, 1), (4, 1), (1, 3), (1, 4), (6, 3), (6, 4), (3, 6), (4, 6)]:
            put(f, 0, x, y, 'fire:1', halo_a)
        # 中：2×2
        c1 = ['fire:3', 'fire:4', 'fire:3', 'fire:2'][f]
        c2 = ['fire:2', 'fire:3', 'fire:2', 'fire:1'][f]
        put(f, 1, 3, 3, c1)
        put(f, 1, 4, 3, c2)
        put(f, 1, 3, 4, c2)
        put(f, 1, 4, 4, 'fire:1')
        put(f, 1, 3, 5, 'fire:1', 150)
        # 小：1 点 + 下方尾迹
        put(f, 2, 4, 3, ['fire:3', 'fire:4', 'fire:2', 'fire:3'][f])
        put(f, 2, 4, 4, 'fire:1')
        if f % 2 == 0:
            put(f, 2, 4, 5, 'fire:1', 140)
        # 火花：点 → 十字 → 点 → 暗
        if f == 1:
            for (x, y) in [(3, 4), (5, 4), (4, 3), (4, 5)]:
                put(f, 3, x, y, 'fire:3')
            put(f, 3, 4, 4, 'fire:4')
        elif f == 3:
            put(f, 3, 4, 4, 'fire:2')
        else:
            put(f, 3, 4, 4, 'fire:4')
    for iy, k in enumerate(kinds):
        for f in range(4):
            frames['%s_%d' % (k, f)] = [f * cell, iy * cell, cell, cell, 4, 4]
        dur = [6, 5, 7, 4][iy]
        anims[k] = [['%s_%d' % (k, f), dur] for f in range(4)]
    meta = {'frames': frames, 'anims': anims,
            'note': '标题画面余烬粒子：每格 8×8，锚点(4,4)为粒子中心。建议运行时随机生成粒子，从画面下方/城堡处向上飘（每帧上移 0.2~0.6px，左右正弦摆动），循环播放对应 anim。'}
    return Image.fromarray(img, 'RGBA'), meta


# ===========================================================================
# 预览 / 主流程
# ===========================================================================
def check(cv, sid):
    cols = cv.colors()
    bad = cols - K.allowed_colors()
    if bad:
        print('  !! %s 含调色板外颜色 %d 个：%s' % (sid, len(bad), list(bad)[:5]))
    if (0, 0, 0) in cols:
        print('  !! %s 含纯黑' % sid)
    return len(cols)


def main(argv):
    want = [a for a in argv if not a.startswith('--')]
    preview = '--no-preview' not in argv
    os.makedirs(OUT_BG, exist_ok=True)
    os.makedirs(PREV, exist_ok=True)
    done = []
    for sid, fn in SCENES.items():
        if want and sid not in want:
            continue
        cv = fn()
        n = check(cv, sid)
        img = cv.image()
        save_indexed(img, os.path.join(OUT_BG, sid + '.png'))
        done.append((sid, img))
        print('bg %-16s %3d 色' % (sid, n))
        if preview:
            upscale(img, 3).save(os.path.join(PREV, sid + '_x3.png'))
            upscale(mock_overlay(img), 2).save(os.path.join(PREV, sid + '_ui.png'))
    if not want:
        with open(os.path.join(OUT_BG, 'index.json'), 'w', encoding='utf-8') as f:
            json.dump({k: DESC[k] for k in SCENES}, f, ensure_ascii=False, indent=1)
    if preview and len(done) > 1:
        contact_sheet([im for _, im in done], 3, 1).save(os.path.join(PREV, '_sheet.png'))
    # Logo / 图标 / 标题画面
    if not want or 'logo' in want:
        logo = make_logo()
        check_rgba(logo, 'logo')
        logo.save(os.path.join(OUT_ASSETS, 'logo.png'))
        print('logo  %dx%d' % logo.size)
        if preview:
            for name, bg in (('logo_dark', (18, 14, 28, 255)), ('logo_light', (200, 196, 210, 255))):
                base = Image.new('RGBA', logo.size, bg)
                base.alpha_composite(logo)
                upscale(base, 4).save(os.path.join(PREV, name + '_x4.png'))
    if not want or 'icon' in want:
        icon = make_icon()
        check_rgba(icon, 'icon')
        icon.save(os.path.join(OUT_ASSETS, 'icon.png'))
        print('icon  %dx%d' % icon.size)
        if preview:
            sheet = Image.new('RGBA', (32 * 8 + 16 + 64, 32 * 8), (200, 196, 210, 255))
            sheet.alpha_composite(upscale(icon, 8), (0, 0))
            sheet.alpha_composite(icon, (32 * 8 + 8, 8))
            dark = Image.new('RGBA', (32, 32), (30, 30, 36, 255))
            dark.alpha_composite(icon)
            sheet.alpha_composite(dark, (32 * 8 + 8, 48))
            sheet.alpha_composite(icon.resize((16, 16), Image.NEAREST), (32 * 8 + 8, 90))
            sheet.save(os.path.join(PREV, 'icon_x8.png'))
    if not want or 'title' in want:
        cv = make_title_bg()
        n = check(cv, 'title_bg')
        img = cv.image()
        save_indexed(img, os.path.join(OUT_ASSETS, 'title_bg.png'))
        print('title_bg %d 色' % n)
        emb, meta = make_title_embers()
        check_rgba(emb, 'title_embers', effect=True)
        emb.save(os.path.join(OUT_ASSETS, 'title_embers.png'))
        with open(os.path.join(OUT_ASSETS, 'title_embers.json'), 'w', encoding='utf-8') as f:
            f.write(dump_meta(meta))
        if preview:
            comp = img.convert('RGBA')
            logo = make_logo()
            comp.alpha_composite(logo, ((320 - logo.width) // 2, TITLE_LOGO_Y))
            upscale(comp, 3).save(os.path.join(PREV, 'title_x3.png'))
            upscale(img, 3).save(os.path.join(PREV, 'title_bg_x3.png'))
            e = Image.new('RGBA', emb.size, (18, 14, 28, 255))
            e.alpha_composite(emb)
            upscale(e, 8).save(os.path.join(PREV, 'title_embers_x8.png'))


def dump_meta(meta):
    """精灵表 JSON：每个帧 / 动画一行（与项目里其他精灵表同一格式）。"""
    out = ['{']
    keys = list(meta.keys())
    for ki, key in enumerate(keys):
        val = meta[key]
        tail = ',' if ki < len(keys) - 1 else ''
        if isinstance(val, dict):
            out.append(' "%s": {' % key)
            items = list(val.items())
            for i, (k, v) in enumerate(items):
                out.append('  "%s": %s%s' % (k, json.dumps(v, ensure_ascii=False), ',' if i < len(items) - 1 else ''))
            out.append(' }' + tail)
        else:
            out.append(' "%s": %s%s' % (key, json.dumps(val, ensure_ascii=False), tail))
    out.append('}')
    nl = chr(10)
    return nl.join(out) + nl


def check_rgba(img, name, effect=False):
    """透明图检查：颜色须在调色板内；alpha 只能是 0 / 255（effect=True 的特效图允许半透明光晕）。"""
    a = np.array(img)
    alpha = a[..., 3]
    vis = alpha > 0
    cols = {tuple(int(v) for v in c) for c in a[vis][:, :3]}
    bad = cols - K.allowed_colors()
    if bad:
        print('  !! %s 含调色板外颜色 %d 个：%s' % (name, len(bad), list(bad)[:5]))
    semi = ((alpha > 0) & (alpha < 255)).sum()
    if semi and not effect:
        print('  !! %s 含半透明像素 %d 个' % (name, semi))
    return len(cols)


if __name__ == '__main__':
    main(sys.argv[1:])
