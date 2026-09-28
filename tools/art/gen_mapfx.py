# -*- coding: utf-8 -*-
"""
《灰烬王冠》地图叠加特效：光标、范围格、移动路径箭头、增援预警、火焰/烟雾、闪光、阴影、
撤离/占领/防守点标记、交谈气泡。

用法：python tools/art/gen_mapfx.py
输出：assets/mapfx.png + assets/mapfx.json（帧格式见 docs/design.md §1），
      放大预览 tools/art/preview/mapfx/mapfx.png

锚点约定（运行时 draw(帧名, x, y) 让 (x,y) 对准锚点）：
  * 16×16 的格子类帧（范围格、箭头、warn、fire、escape/seize/defend）锚点 (0,0)：传格子左上角。
  * cursor*：24×24，锚点 (4,4)：传格子左上角，四角括号正好框住该格。
  * smoke*：16×24，锚点 (0,8)：传格子左上角，烟从格底往上冒出 8px。
  * sparkle*：8×8，锚点 (4,4)：传闪光中心点。
  * shadow：16×6，锚点 (8,3)：传单位脚底中心。
  * talk*：10×11，锚点 (1,10)（气泡尾尖）：建议传 (格x+11, 格y+3)，气泡出现在单位头顶右上。
"""
import os
import sys
import json
import math

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from palette import PAL, INK, INK2, hx  # noqa: E402

OUT_PNG = os.path.join(ROOT, 'assets', 'mapfx.png')
OUT_JSON = os.path.join(ROOT, 'assets', 'mapfx.json')
PREV_DIR = os.path.join(HERE, 'preview', 'mapfx')

TB = PAL['team_blue']; TR = PAL['team_red']; TG = PAL['team_green']
GO = PAL['gold']; FI = PAL['fire']; GY = PAL['grey']; ST = PAL['stone']
CW = PAL['cloth_white']; WO = PAL['wood']; SK = PAL['cloth_sky']
WHITE = hx('#ffffff')
# 敌方威胁范围用的紫红色阶（与主调色板同样的明度层次）
THREAT = [hx(c) for c in ('#2c0a24', '#5a1446', '#8c2468', '#c0407a', '#e878b0', '#ffc0e0')]


def rgba(c, a=1.0):
    return (c[0], c[1], c[2], int(round(255 * a)))


class Frame:
    def __init__(self, w, h, ax=0, ay=0):
        self.img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        self.px = self.img.load()
        self.w, self.h = w, h
        self.ax, self.ay = ax, ay

    def put(self, x, y, c, a=1.0):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[x, y] = rgba(c, a) if len(c) == 4 and a != 1.0 else (c if len(c) == 4 else rgba(c, a))

    def get(self, x, y):
        return self.px[x, y]


# ------------------------------------------------------------------ 光标
def make_cursor(d, bright):
    """四角括号：臂长 5、粗 2，外描边 INK；d 为向外扩张的像素数。"""
    f = Frame(24, 24, 4, 4)
    core = WHITE if bright else GO[4]
    shade = GO[3] if bright else GO[2]
    pts = {}
    # 格子占 (4..19)；括号贴在格外 1px 处，再向外扩 d
    lo = 4 - 2 - d
    hi_ = 19 + 1 + d
    L = 5
    for (cx, cy, sx, sy) in ((lo, lo, 1, 1), (hi_, lo, -1, 1), (lo, hi_, 1, -1), (hi_, hi_, -1, -1)):
        for i in range(L):
            for t in range(2):
                pts[(cx + sx * i, cy + sy * t)] = 'c'
                pts[(cx + sx * t, cy + sy * i)] = 'c'
    # 内侧（朝格子的一侧）用暗一级，做出厚度
    out = {}
    for (x, y) in pts:
        inner = (4 <= x <= 19 and 4 <= y <= 19)
        out[(x, y)] = shade if (x in (lo + 1, hi_ - 1) or y in (lo + 1, hi_ - 1)) and (x, y) not in (
            (lo + 1, lo + 1), (hi_ - 1, lo + 1), (lo + 1, hi_ - 1), (hi_ - 1, hi_ - 1)) else core
        if inner:
            out[(x, y)] = shade
    for (x, y), c in out.items():
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                k = (x + ox, y + oy)
                if k not in out:
                    f.put(k[0], k[1], INK)
    for (x, y), c in out.items():
        f.put(x, y, c)
    return f


# ------------------------------------------------------------------ 范围格
def make_range(ramp, i, n=4):
    """半透明方格：1px 亮边（四角留空成圆角）+ 斜向流光带。"""
    f = Frame(16, 16, 0, 0)
    fill = ramp[4] if len(ramp) > 5 else ramp[3]
    light = ramp[5] if len(ramp) > 5 else ramp[4]
    pos = -6 + i * 10
    for y in range(16):
        for x in range(16):
            edge = x in (0, 15) or y in (0, 15)
            corner = (x in (0, 15)) and (y in (0, 15))
            if corner:
                continue
            if edge:
                f.put(x, y, light, 0.82)
                continue
            d = (x + y) - pos
            if 0 <= d <= 2:
                f.put(x, y, light, 0.66 if d == 1 else 0.58)
            elif x in (1, 14) or y in (1, 14):
                f.put(x, y, fill, 0.58)
            else:
                f.put(x, y, fill, 0.48)
    return f


# ------------------------------------------------------------------ 移动路径箭头
AO = TB[1]      # 描边
AE = TB[4]      # 边缘
AF = TB[5]      # 填充
AW = WHITE      # 高光
SECTION = [AO, AE, AF, AW, AE, AO]   # 6px 截面（从一侧到另一侧），对称便于拐角衔接


def arrow_seg(f, horiz, x0=0, x1=15):
    for t in range(x0, x1 + 1):
        for k, c in enumerate(SECTION):
            if horiz:
                f.put(t, 5 + k, c)
            else:
                f.put(5 + k, t, c)


def arrow_corner(f, cxp, cyp):
    """以格角 (cxp,cyp) 为圆心的四分之一圆环（半径 5..11），把两条边的中段连起来。"""
    for y in range(16):
        for x in range(16):
            r = math.hypot(x + 0.5 - cxp, y + 0.5 - cyp)
            k = int(math.floor(r - 5.0))
            if 0 <= k < 6:
                f.put(x, y, SECTION[k])


def rot(f, times):
    img = f.img
    for _ in range(times):
        img = img.transpose(Image.ROTATE_270)
    g = Frame(16, 16, 0, 0)
    g.img = img
    g.px = img.load()
    return g


def arrow_head_up():
    f = Frame(16, 16, 0, 0)
    # 箭杆：从下边进来到 y=10
    arrow_seg(f, False, 10, 15)
    # 箭头三角：底边 y=10（x 1..14），尖 y=1
    tip, base = 1, 10
    for y in range(tip, base + 1):
        t = (y - tip) / (base - tip)
        half = 0.5 + 6.5 * t
        xl = int(round(7.5 - half))
        xr = int(round(7.5 + half))
        for x in range(xl, xr + 1):
            if x == xl or x == xr or y == base:
                c = AO
            elif x == xl + 1 or y == base - 1:
                c = AE if y == base - 1 else AW
            elif x == xr - 1:
                c = AE
            else:
                c = AF
            f.put(x, y, c)
    f.put(7, tip - 1, AO)
    f.put(8, tip - 1, AO)
    # 箭杆与三角底边相接处保持截面
    for k, c in enumerate(SECTION):
        if c != AO:
            f.put(5 + k, base, c)
    return f


def arrow_start_up():
    f = Frame(16, 16, 0, 0)
    arrow_seg(f, False, 0, 8)
    # 起点圆帽（中心 7.5,8.5 半径 4.2）
    cx, cy, r = 8.0, 8.5, 4.3
    for y in range(16):
        for x in range(16):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            if d <= r:
                if d > r - 1.0:
                    c = AO
                elif d > r - 2.0:
                    c = AE
                else:
                    c = AF
                if y < 8 and 5 <= x <= 10:
                    c = SECTION[x - 5]
                f.put(x, y, c)
    # 圆帽中心高光
    f.put(7, 8, AW)
    f.put(8, 8, AW)
    f.put(7, 9, AW)
    return f


# ------------------------------------------------------------------ 标记
def make_warn(bright):
    f = Frame(16, 16, 0, 0)
    cx, cy, r = 8.0, 8.0, 6.6 if not bright else 7.2
    body, hi, dk = (TR[3], TR[4], TR[2]) if not bright else (TR[4], TR[5], TR[3])
    for y in range(16):
        for x in range(16):
            d = abs(x + 0.5 - cx) + abs(y + 0.5 - cy)
            if d <= r:
                if d > r - 1.0:
                    c = TR[1] if not bright else TR[2]
                elif (x + 0.5 - cx) + (y + 0.5 - cy) < -1.8 and d > r - 2.5:
                    c = hi
                elif (x + 0.5 - cx) + (y + 0.5 - cy) > 1.8 and d > r - 2.5:
                    c = dk
                else:
                    c = body
                f.put(x, y, c)
    for y in range(4, 10):
        f.put(7, y, WHITE)
        f.put(8, y, GY[4] if y > 4 else WHITE)
    f.put(7, 11, WHITE)
    f.put(8, 11, GY[4])
    f.put(7, 12, GY[4])
    f.put(8, 12, GY[3])
    return f


def make_fire(i):
    """燃烧火焰：3 道火舌从格底升起，逐帧起伏摆动。"""
    f = Frame(16, 16, 0, 0)
    tongues = [(4.0, 9.0, 3.2, 0.0), (8.5, 13.0, 3.8, 1.7), (12.5, 8.0, 3.0, 3.4)]
    layers = [(1.00, FI[0]), (0.78, FI[1]), (0.55, FI[2]), (0.33, FI[3]), (0.14, FI[4])]
    grid = {}
    for (tx, th, tw, ph) in tongues:
        a = i * math.pi / 2 + ph
        h = th + math.sin(a) * 2.0
        sway = math.sin(a + 1.3) * 1.2
        for y in range(16):
            yy = 15.5 - y          # 距格底高度
            if yy > h + 0.5:
                continue
            t = max(0.0, min(1.0, yy / h))   # 0 底部 .. 1 尖
            wid = tw * (1 - t) ** 0.8 * (0.8 + 0.6 * math.sin(math.pi * min(1.0, t + 0.25)))
            cxp = tx + sway * t * t
            for x in range(16):
                dx = abs(x + 0.5 - cxp)
                if dx <= wid + 0.3:
                    # 越靠中心、越靠下越亮
                    v = (dx / max(0.6, wid + 0.3)) * 0.7 + t * 0.55
                    lv = 0
                    for li, (thr, c) in enumerate(layers):
                        if v <= thr:
                            lv = li
                    grid[(x, y)] = max(grid.get((x, y), 0), lv)
    for (x, y), lv in grid.items():
        f.put(x, y, layers[lv][1])
    # 火星
    sparks = [(3, 3), (11, 2), (7, 1), (13, 5)]
    sx, sy = sparks[i % 4]
    f.put(sx, sy - (i % 2), FI[3])
    return f


def make_smoke(i):
    """16×24 烟雾：三团灰烟自下而上逐帧上升、变淡。"""
    f = Frame(16, 24, 0, 8)
    puffs = []
    for k in range(3):
        ph = (i + k * 4 / 3) % 4 / 4.0          # 0..1 生命周期
        y = 20 - ph * 18
        x = 7.5 + math.sin(ph * math.pi * 1.5 + k) * 2.5
        r = 2.2 + ph * 2.6
        alpha = 0.78 * (1 - ph) ** 0.6
        puffs.append((x, y, r, alpha))
    puffs.sort(key=lambda p: -p[1])
    for (px, py, r, al) in puffs:
        for y in range(24):
            for x in range(16):
                d = math.hypot(x + 0.5 - px, y + 0.5 - py)
                if d <= r:
                    lit = (x + 0.5 - px) + (y + 0.5 - py) < -r * 0.3
                    c = GY[3] if lit else (GY[2] if d < r * 0.75 else GY[1])
                    a = al * (0.75 if d > r - 0.8 else 1.0)
                    old = f.get(x, y)
                    if old[3] < int(255 * a):
                        f.put(x, y, c, a)
    return f


def make_sparkle(i):
    f = Frame(8, 8, 4, 4)
    c, g = WHITE, GO[4]
    if i == 0:
        f.put(3, 3, c); f.put(4, 4, g, 0.8); f.put(3, 4, g, 0.8); f.put(4, 3, g, 0.8)
    elif i in (1, 3):
        for d in (-1, 0, 1):
            f.put(3 + d, 3, g if d else c)
            f.put(3, 3 + d, g if d else c)
        if i == 3:
            f.put(3, 3, g)
    else:
        for d in range(-3, 4):
            a = 1.0 if abs(d) <= 1 else 0.7
            f.put(3 + d, 3, c if abs(d) <= 1 else g, a)
            f.put(3, 3 + d, c if abs(d) <= 1 else g, a)
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            f.put(3 + dx, 3 + dy, g, 0.8)
    return f


def make_shadow():
    f = Frame(16, 6, 8, 3)
    for y in range(6):
        for x in range(16):
            d = ((x + 0.5 - 8) / 7.5) ** 2 + ((y + 0.5 - 3) / 2.9) ** 2
            if d <= 1:
                f.put(x, y, INK, 0.42 if d < 0.55 else 0.28)
    return f


def make_escape(i):
    """撤离点：绿色三角旗（旗杆 + 飘动的旗面，旗上白色箭头）+ 地面光圈。"""
    f = Frame(16, 16, 0, 0)
    for x in range(2, 14):
        for y in (13, 14, 15):
            d = ((x + 0.5 - 8) / 6) ** 2 + ((y + 0.5 - 14) / 1.8) ** 2
            if d <= 1:
                f.put(x, y, TG[4] if d > 0.55 else TG[5], 0.75 if d > 0.55 else 0.55)
    # 旗杆
    for y in range(1, 15):
        f.put(3, y, INK2)
        f.put(4, y, WO[3] if y > 1 else GO[4])
        f.put(5, y, INK2 if y < 3 or y > 9 else WO[1])
    f.put(4, 0, INK2)
    # 旗面：三角形，根部 x=5..6 高 8 行（y 2..9），尖在 x=14
    sag = 0 if i == 0 else 1
    for x in range(5, 15):
        t = (x - 5) / 9.0
        top = 2 + t * 3.5 + (sag * t if x > 8 else 0)
        bot = 9 - t * 3.5 + (sag * t if x > 8 else 0)
        yt = int(round(top))
        yb = int(round(bot))
        for y in range(yt, yb + 1):
            if y == yt or y == yb or x == 14:
                c = TG[0]
            elif y == yt + 1:
                c = TG[4]
            elif y == yb - 1:
                c = TG[1]
            else:
                c = TG[3] if x < 11 else TG[2]
            f.put(x, y, c)
    # 白色箭头（出口方向）
    oy = 0 if i == 0 else 0
    for (x, y) in ((7, 4), (8, 5), (9, 6), (8, 7), (7, 8), (6, 5), (7, 5), (6, 6), (7, 6), (8, 6), (6, 7), (7, 7)):
        pass
    for (x, y) in ((7, 4), (8, 5), (9, 6), (8, 7), (7, 8)):
        f.put(x, y + oy, WHITE)
    return f


def make_seize(i):
    """占领点：金色小王冠。"""
    f = Frame(16, 16, 0, 0)
    rows = [
        '..o....oo....o..',
        '.oyo..oyyo..oyo.',
        '.oyo..oyyo..oyo.',
        '.oygo.oyyo.ogyo.',
        '.oyygooyyooggyo.',
        '.oyyggggggggggo.',
        '.oyggggggggggmo.',
        '.oyrgggbbgggrmo.',
        '.oyggggggggggmo.',
        '.ommmmmmmmmmmmo.',
        '..oooooooooooo..',
    ]
    leg = {'o': GO[0], 'y': GO[4], 'g': GO[3], 'm': GO[2], 'r': TR[4], 'b': SK[4]}
    oy = 3
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != '.':
                f.put(x, y + oy, leg[ch])
    if i == 1:
        # 闪光
        for (x, y) in ((3, 4), (2, 5), (4, 5), (3, 6)):
            f.put(x, y, WHITE)
        f.put(8, oy + 1, WHITE)
    # 底座阴影
    for x in range(3, 13):
        f.put(x, 15, INK, 0.3)
    return f


def make_defend(i):
    """防守点：蓝色盾牌，中间白色十字纹。"""
    f = Frame(16, 16, 0, 0)
    for y in range(2, 15):
        t = (y - 2) / 12.0
        half = 6.0 if t < 0.5 else 6.0 * (1 - (t - 0.5) * 1.9)
        if half < 0.5:
            half = 0.5
        xl = int(round(8 - half))
        xr = int(round(8 + half)) - 1
        for x in range(xl, xr + 1):
            if x == xl or x == xr or y == 2:
                c = TB[1]
            elif x == xl + 1 or y == 3:
                c = TB[5] if i == 1 else TB[4]
            elif x == xr - 1:
                c = TB[2]
            else:
                c = TB[3] if x < 8 else TB[2]
                if i == 1 and x < 8:
                    c = TB[4]
            f.put(x, y, c)
    f.put(8, 14, TB[1]); f.put(7, 14, TB[1])
    for y in range(5, 12):
        f.put(7, y, WHITE if y < 9 else GY[4])
        f.put(8, y, GY[4])
    for x in range(5, 11):
        f.put(x, 7, WHITE if x < 8 else GY[4])
    return f


def make_talk(i):
    """交谈气泡：10×11，i=1 时整体上移 1px 做跳动。"""
    f = Frame(10, 11, 1, 10)
    oy = 0 if i == 0 else -1
    rows = [
        '.oooooooo.',
        'owwwwwwwwo',
        'owkwwkwwko',
        'owwwwwwwwo',
        'owwwwwwwso',
        '.oswwssso.',
        '..osoooo..',
        '..oo......',
        '.o........',
    ]
    leg = {'o': INK, 'w': WHITE, 'k': INK2, 's': CW[3]}
    base = 1
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != '.':
                f.put(x, y + base + oy, leg[ch])
    return f


# ------------------------------------------------------------------ 打包
def build():
    frames = {}
    order = []

    def add(name, fr):
        frames[name] = fr
        order.append(name)

    for i, (d, b) in enumerate(((0, True), (1, True), (2, False), (1, False))):
        add('cursor%d' % i, make_cursor(d, b))
    for nm, ramp in (('move', TB), ('attack', TR), ('staff', TG), ('threat', THREAT)):
        for i in range(4):
            add('%s%d' % (nm, i), make_range(ramp, i))
    base = Frame(16, 16)
    arrow_seg(base, True)
    add('arrow_h', base)
    v = Frame(16, 16)
    arrow_seg(v, False)
    add('arrow_v', v)
    for nm, (cx, cy) in (('arrow_ne', (16, 0)), ('arrow_nw', (0, 0)), ('arrow_se', (16, 16)), ('arrow_sw', (0, 16))):
        fr = Frame(16, 16)
        arrow_corner(fr, cx, cy)
        add(nm, fr)
    hu = arrow_head_up()
    add('arrow_head_u', hu)
    add('arrow_head_r', rot(hu, 1))
    add('arrow_head_d', rot(hu, 2))
    add('arrow_head_l', rot(hu, 3))
    su = arrow_start_up()
    add('arrow_start_u', su)
    add('arrow_start_r', rot(su, 1))
    add('arrow_start_d', rot(su, 2))
    add('arrow_start_l', rot(su, 3))
    add('warn0', make_warn(False))
    add('warn1', make_warn(True))
    for i in range(4):
        add('fire%d' % i, make_fire(i))
    for i in range(4):
        add('smoke%d' % i, make_smoke(i))
    for i in range(4):
        add('sparkle%d' % i, make_sparkle(i))
    add('shadow', make_shadow())
    for i in range(2):
        add('escape%d' % i, make_escape(i))
    for i in range(2):
        add('seize%d' % i, make_seize(i))
    for i in range(2):
        add('defend%d' % i, make_defend(i))
    for i in range(2):
        add('talk%d' % i, make_talk(i))

    # 按行打包：宽 256，行高取该行最高帧，帧间留 1px 透明缝
    SW = 256
    x = y = rowh = 0
    pos = {}
    for nm in order:
        fr = frames[nm]
        if x + fr.w > SW:
            x = 0
            y += rowh + 1
            rowh = 0
        pos[nm] = (x, y)
        x += fr.w + 1
        rowh = max(rowh, fr.h)
    H = y + rowh
    sheet = Image.new('RGBA', (SW, H), (0, 0, 0, 0))
    meta = {'frames': {}, 'anims': {}}
    for nm in order:
        fr = frames[nm]
        px_, py_ = pos[nm]
        sheet.paste(fr.img, (px_, py_))
        meta['frames'][nm] = [px_, py_, fr.w, fr.h, fr.ax, fr.ay]
    A = meta['anims']
    A['cursor'] = [['cursor0', 10], ['cursor1', 6], ['cursor2', 10], ['cursor3', 6]]
    for nm in ('move', 'attack', 'staff', 'threat'):
        A[nm] = [['%s%d' % (nm, i), 8] for i in range(4)] + [['%s0' % nm, 24]]
    A['warn'] = [['warn0', 20], ['warn1', 20]]
    A['fire'] = [['fire%d' % i, 6] for i in range(4)]
    A['smoke'] = [['smoke%d' % i, 9] for i in range(4)]
    A['sparkle'] = [['sparkle0', 4], ['sparkle1', 4], ['sparkle2', 6], ['sparkle3', 4]]
    A['escape'] = [['escape0', 18], ['escape1', 18]]
    A['seize'] = [['seize0', 40], ['seize1', 8]]
    A['defend'] = [['defend0', 30], ['defend1', 12]]
    A['talk'] = [['talk0', 24], ['talk1', 24]]
    return sheet, meta, frames, order


def preview_sheet(frames, order, path):
    """把每一帧放大 4 倍排在一起，带格子背景，便于检查。"""
    sc = 4
    cols = 10
    cell = 26
    rows = (len(order) + cols - 1) // cols
    img = Image.new('RGBA', (cols * cell * sc, rows * cell * sc), (46, 60, 40, 255))
    grass = hx('#84b84a')
    for i, nm in enumerate(order):
        fr = frames[nm]
        cx = (i % cols) * cell
        cy = (i // cols) * cell
        tile = Image.new('RGBA', (cell, cell), grass)
        # 16×16 参考格
        for yy in range(16):
            for xx in range(16):
                if (xx + yy) % 2 == 0:
                    tile.putpixel((5 + xx, 5 + yy), hx('#7aae44'))
        tile.alpha_composite(fr.img, (5 - fr.ax if fr.ax <= 5 else 0, 5 - fr.ay if fr.ay <= 5 else 0)
                             if nm not in ('shadow',) and not nm.startswith('sparkle') and not nm.startswith('talk')
                             else (13 - fr.ax, 13 - fr.ay))
        img.paste(tile.resize((cell * sc, cell * sc), Image.NEAREST), (cx * sc, cy * sc))
    img.save(path)


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    sheet, meta, frames, order = build()
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    sheet.save(OUT_PNG)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    os.makedirs(PREV_DIR, exist_ok=True)
    preview_sheet(frames, order, os.path.join(PREV_DIR, 'mapfx.png'))
    print('mapfx: %d 帧 -> %s (%dx%d)' % (len(order), os.path.relpath(OUT_PNG, ROOT), sheet.width, sheet.height))


if __name__ == '__main__':
    main()
