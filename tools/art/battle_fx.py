# -*- coding: utf-8 -*-
"""
战斗特效与投射物（battle_fx.png / .json）。
帧名 {fx}{i}；投射物朝左飞（引擎可水平镜像）；锚点在特效中心（落雷/星辉/治疗为“命中点”，见 ANCHOR_NOTE）。
所有帧宽度为偶数且锚点 x = w/2，便于引擎以锚点为轴镜像。
特效允许半透明光晕，核心像素仍取自调色板。
"""
import math
import os
import json
import numpy as np
from PIL import Image
from palette import PAL, INK, INK2

FIRE = PAL['fire']          # 暗红→白黄
MB = PAL['magic_blue']
MD = PAL['magic_dark']
HL = PAL['heal']
GREY = PAL['grey']
GOLD = PAL['gold']
WHITE = GREY[5]

ANCHOR_NOTE = ('锚点：投射物/火花/刀光/扬尘/暗/火焰爆炸在图形中心；'
               'thunder 与 light 的锚点在命中点（光束落下的位置），heal 的锚点在目标身体中心（光柱中段）。')


class FX:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.a = np.zeros((h, w, 4), np.float64)   # 预乘前的 RGBA（0~1）
        yy, xx = np.mgrid[0:h, 0:w]
        self.x = xx + 0.5
        self.y = yy + 0.5

    def put(self, mask, color, alpha=1.0):
        """把颜色按 alpha 叠加到 mask 区域（over 合成）。"""
        c = np.array(color[:3], np.float64) / 255.0
        if np.isscalar(alpha):
            al = np.full((self.h, self.w), float(alpha))
        else:
            al = alpha
        al = np.where(mask, al, 0.0)
        src_a = al[..., None]
        dst = self.a
        out_a = src_a[..., 0] + dst[..., 3] * (1 - src_a[..., 0])
        rgb = (c[None, None, :] * src_a + dst[..., :3] * dst[..., 3:4] * (1 - src_a)) / np.maximum(out_a[..., None], 1e-6)
        dst[..., :3] = np.where(out_a[..., None] > 0, rgb, dst[..., :3])
        dst[..., 3] = out_a

    def disk(self, cx, cy, r, color, alpha=1.0):
        self.put((self.x - cx) ** 2 + (self.y - cy) ** 2 <= r * r, color, alpha)

    def ell(self, cx, cy, rx, ry, color, alpha=1.0, ang=0.0):
        ca, sa = math.cos(ang), math.sin(ang)
        u = (self.x - cx) * ca + (self.y - cy) * sa
        v = -(self.x - cx) * sa + (self.y - cy) * ca
        self.put((u / rx) ** 2 + (v / ry) ** 2 <= 1.0, color, alpha)

    def ring(self, cx, cy, r0, r1, color, alpha=1.0):
        d2 = (self.x - cx) ** 2 + (self.y - cy) ** 2
        self.put((d2 <= r1 * r1) & (d2 >= r0 * r0), color, alpha)

    def poly(self, pts, color, alpha=1.0):
        inside = np.zeros((self.h, self.w), bool)
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            if y0 == y1:
                continue
            cond = (y0 > self.y) != (y1 > self.y)
            xint = (x1 - x0) * (self.y - y0) / (y1 - y0) + x0
            inside ^= cond & (self.x < xint)
        self.put(inside, color, alpha)

    def line(self, p0, p1, color, alpha=1.0, width=1):
        m = np.zeros((self.h, self.w), bool)
        x0, y0 = int(math.floor(p0[0])), int(math.floor(p0[1]))
        x1, y1 = int(math.floor(p1[0])), int(math.floor(p1[1]))
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            for ox in range(width):
                for oy in range(width):
                    xx, yy = x0 + ox - width // 2, y0 + oy - width // 2
                    if 0 <= xx < self.w and 0 <= yy < self.h:
                        m[yy, xx] = True
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy
        self.put(m, color, alpha)

    def pix(self, x, y, color, alpha=1.0):
        x, y = int(x), int(y)
        if 0 <= x < self.w and 0 <= y < self.h:
            m = np.zeros((self.h, self.w), bool)
            m[y, x] = True
            self.put(m, color, alpha)

    def outline(self, color=INK, thresh=0.5):
        """给不透明部分加 1px 外描边（投射物用）。"""
        solid = self.a[..., 3] >= thresh
        d = solid.copy()
        d[1:] |= solid[:-1]
        d[:-1] |= solid[1:]
        d[:, 1:] |= solid[:, :-1]
        d[:, :-1] |= solid[:, 1:]
        self.put(d & ~solid, color, 1.0)

    def img(self):
        out = np.zeros((self.h, self.w, 4), np.uint8)
        out[..., :3] = np.clip(self.a[..., :3] * 255 + 0.5, 0, 255)
        al = self.a[..., 3]
        # 近乎不透明的像素直接实心化；极淡的像素丢弃，避免脏边
        al = np.where(al > 0.92, 1.0, al)
        al = np.where(al < 0.08, 0.0, al)
        out[..., 3] = np.clip(al * 255 + 0.5, 0, 255)
        return out


def rng(seed):
    return np.random.RandomState(seed)


def snap_palette(img, pal):
    """把不透明像素的颜色吸附到给定调色板（保持 alpha）。"""
    cols = np.array([c[:3] for c in pal], np.float64)
    rgb = img[..., :3].astype(np.float64)
    d = ((rgb[..., None, :] - cols[None, None, :, :]) ** 2).sum(-1)
    idx = d.argmin(-1)
    out = img.copy()
    out[..., :3] = cols[idx].astype(np.uint8)
    out[img[..., 3] == 0] = 0
    return out


FX_PAL = [INK, INK2] + [c for k in ('fire', 'magic_blue', 'magic_dark', 'heal', 'grey', 'gold', 'wood', 'steel',
                                    'earth', 'rock', 'cloth_white', 'cloth_sky', 'team_red') for c in PAL[k]]


# ================================================================ 投射物
def fx_arrow():
    f = FX(20, 8)
    cy = 3.5
    f.line((4, cy), (16, cy), PAL['wood'][3])
    f.line((5, cy + 1), (15, cy + 1), PAL['wood'][2])
    f.poly([(0.5, cy + 0.5), (4.8, cy - 2.2), (3.8, cy + 0.5), (4.8, cy + 3.2)], PAL['steel'][4])
    f.pix(2, 4, PAL['steel'][2])
    f.pix(3, 4, PAL['steel'][3])
    f.line((14, cy - 2), (18, cy - 2), PAL['cloth_white'][4])
    f.line((13, cy - 1), (17, cy - 1), PAL['cloth_white'][3])
    f.line((14, cy + 3), (18, cy + 3), PAL['team_red'][3])
    f.line((13, cy + 2), (17, cy + 2), PAL['team_red'][2])
    f.outline()
    return [f.img()]


def fx_javelin():
    f = FX(30, 8)
    cy = 3.5
    f.line((6, cy), (27, cy), PAL['wood'][4])
    f.line((6, cy + 1), (27, cy + 1), PAL['wood'][2])
    f.poly([(0.5, cy + 0.6), (4.0, cy - 2.0), (7.5, cy - 0.6), (7.5, cy + 1.8), (4.0, cy + 3.2)], PAL['steel'][3])
    f.line((1, cy), (6, cy), PAL['steel'][4])
    f.line((7, cy - 1), (8, cy + 2), PAL['iron'][2])
    f.outline()
    return [f.img()]


def fx_handaxe():
    """手斧旋转 4 帧：用战斗木偶的斧头部件在 4 个角度渲染，按包围盒中心裁成 20x20。"""
    import battle_rig as R
    from battle_body import Frame, weapon_parts
    out = []
    for k, ang in enumerate((90, 0, -90, 180)):
        F = Frame()
        weapon_parts(F, 'handaxe', (48, 40), ang, dict(kind='handaxe'), 60)
        img = R.render(F.parts, [])
        ys, xs = np.nonzero(img[..., 3])
        cx = (xs.min() + xs.max() + 1) // 2
        cy = (ys.min() + ys.max() + 1) // 2
        crop = img[cy - 10:cy + 10, cx - 10:cx + 10].copy()
        f = FX(20, 20)
        a0 = math.radians([-60, -150, 120, 30][k])
        for t in range(4):
            aa = a0 + t * 0.4
            f.pix(10 + math.cos(aa) * 8.5, 10 + math.sin(aa) * 8.5, PAL['cloth_sky'][4], 0.6 - t * 0.13)
        base = f.img()
        m = crop[..., 3] > 0
        base[m] = crop[m]
        out.append(base)
    return out


def flame_mask(f, cx, cy, r, t, seed, tongues=7, amp=0.35, rise=0.0):
    """噪声火焰：极坐标半径随角度起伏，rise 使上方拉长。"""
    rs = rng(seed)
    ph = rs.uniform(0, 6.28, 4)
    dx = f.x - cx
    dy = f.y - cy
    th = np.arctan2(dy, dx)
    d = np.sqrt(dx * dx + dy * dy)
    wob = (np.sin(th * tongues + ph[0] + t * 1.7) * 0.6 + np.sin(th * (tongues + 3) + ph[1] - t * 2.3) * 0.4)
    up = np.clip(-np.sin(th), 0, 1)  # 上方
    rr = r * (1 + amp * wob + rise * up)
    return d / np.maximum(rr, 1e-3)


def fx_fireball():
    out = []
    for k in range(3):
        f = FX(28, 18)
        cx, cy = 7.5, 9.0
        # 尾焰：向右拖长的椭圆火舌
        for j in range(4):
            L = 14 - j * 3 + (k % 2) * 2
            f.ell(cx + 5 + L * 0.45, cy + (j - 1.5) * 1.3 * (1 if k != 1 else -1), L * 0.55, 2.6 - j * 0.4,
                  FIRE[1 + (j % 2)], 0.9)
        d = flame_mask(f, cx, cy, 6.2, k * 2.0, 11 + k, tongues=6, amp=0.22)
        f.put(d < 1.0, FIRE[1])
        f.put(d < 0.85, FIRE[2])
        f.put(d < 0.62, FIRE[3])
        f.put(d < 0.36, FIRE[4])
        # 外发光
        dd = np.sqrt((f.x - cx) ** 2 + (f.y - cy) ** 2)
        f.put((dd < 9.5) & (d >= 1.0), FIRE[2], 0.25)
        out.append(snap_or_glow(f.img()))
    return out


def snap_or_glow(img):
    """不透明像素吸附调色板，半透明光晕保留颜色。"""
    solid = img[..., 3] == 255
    sn = snap_palette(img, FX_PAL)
    out = img.copy()
    out[solid] = sn[solid]
    return out


def small_flame(f, x, y, h, w, cols, alpha=1.0):
    """向上的小火舌：底部圆、顶部尖。cols = (外, 中, 内)。"""
    f.ell(x, y, w, w * 0.9, cols[0], alpha)
    f.poly([(x - w, y), (x + w, y), (x + w * 0.2, y - h), (x - w * 0.3, y - h * 0.7)], cols[0], alpha)
    f.ell(x, y + 0.3, w * 0.6, w * 0.55, cols[1], alpha)
    f.poly([(x - w * 0.6, y), (x + w * 0.6, y), (x + w * 0.1, y - h * 0.65)], cols[1], alpha)
    if len(cols) > 2:
        f.ell(x, y + 0.6, w * 0.3, w * 0.3, cols[2], alpha)


def fx_fire_burst():
    out = []
    N = 8
    for k in range(N):
        f = FX(60, 60)
        cx, cy = 30, 32
        t = k / (N - 1)
        if k == 0:
            f.disk(cx, cy, 9, FIRE[3], 0.35)
            f.disk(cx, cy, 5, FIRE[4])
            f.disk(cx, cy, 2.5, WHITE)
        elif k <= 4:
            r = [0, 11, 16, 19, 21][k]
            rise = [0, 0.1, 0.25, 0.4, 0.55][k]
            d = flame_mask(f, cx, cy + k * 0.8, r, k * 1.3, 5 + k, tongues=7, amp=0.28 + t * 0.15, rise=rise)
            core = max(0.0, 0.55 - t * 0.6)
            f.put(d < 1.25, FIRE[2], 0.3 * (1 - t))
            f.put(d < 1.0, FIRE[1])
            f.put(d < 0.86, FIRE[2])
            f.put(d < 0.66, FIRE[3] if k < 4 else FIRE[2])
            if core > 0:
                f.put(d < core, FIRE[4])
        else:
            # 火球散开成几簇向上飘的火舌 + 余烬
            rs = rng(50 + k)
            n = [0, 0, 0, 0, 0, 7, 6, 4][k]
            scale = [0, 0, 0, 0, 0, 1.0, 0.75, 0.5][k]
            for j in range(n):
                a = j / n * 6.28 + rs.uniform(-0.3, 0.3)
                rr = rs.uniform(8, 15) * (1 + (k - 5) * 0.25)
                x = cx + math.cos(a) * rr
                y = cy + math.sin(a) * rr * 0.7 - (k - 4) * 3.5
                h = rs.uniform(7, 11) * scale
                w = rs.uniform(2.6, 3.8) * scale
                cols = (FIRE[0], FIRE[1], FIRE[2]) if k < 7 else (FIRE[0], FIRE[1])
                small_flame(f, x, y, h, max(1.2, w), cols)
            if k == 5:
                d = flame_mask(f, cx, cy + 3, 9, 7.0, 91, tongues=6, amp=0.3, rise=0.5)
                f.put(d < 1.0, FIRE[1])
                f.put(d < 0.7, FIRE[2])
            for j in range(8 + k):
                a = rs.uniform(-3.1, 0.1)
                rr = rs.uniform(12, 27)
                f.pix(cx + math.cos(a) * rr, cy + math.sin(a) * rr - (k - 4) * 2, FIRE[3 + (j % 2)])
        out.append(snap_or_glow(f.img()))
    return out


def bolt_points(x0, y0, x1, y1, seed, jag=5.0, steps=10):
    rs = rng(seed)
    pts = [(x0, y0)]
    for i in range(1, steps):
        t = i / steps
        x = x0 + (x1 - x0) * t + rs.uniform(-jag, jag)
        y = y0 + (y1 - y0) * t + rs.uniform(-2, 2)
        pts.append((x, y))
    pts.append((x1, y1))
    return pts


def draw_bolt(f, pts, core=WHITE, glow=MB[3], edge=MB[2], width=3, glow_a=0.35):
    for a, b in zip(pts, pts[1:]):
        f.line(a, b, edge, 0.6, width=width + 2)
    for a, b in zip(pts, pts[1:]):
        f.line(a, b, glow, 1.0, width=width)
    for a, b in zip(pts, pts[1:]):
        f.line(a, b, core, 1.0, width=max(1, width - 2))


def fx_thunder():
    """落雷：48x120，锚点在命中点 (24, 110)。"""
    out = []
    W_, H_ = 48, 120
    gx, gy = 24, 110
    for k in range(6):
        f = FX(W_, H_)
        if k == 0:
            # 预闪：细线 + 天顶亮点
            pts = bolt_points(gx + 2, 0, gx, gy - 30, 7, jag=3, steps=8)
            for a, b in zip(pts, pts[1:]):
                f.line(a, b, MB[4], 0.8)
            f.disk(gx + 2, 2, 4, MB[3], 0.5)
        elif k in (1, 2, 3):
            seed = [0, 21, 21, 33][k]
            pts = bolt_points(gx + 3, -2, gx, gy, seed, jag=6, steps=11)
            draw_bolt(f, pts, width=3 if k != 2 else 5)
            # 分叉
            rs = rng(seed + 5)
            for j in range(2 + k):
                i = rs.randint(2, len(pts) - 3)
                p = pts[i]
                q = (p[0] + rs.uniform(-14, 14), p[1] + rs.uniform(8, 20))
                br = bolt_points(p[0], p[1], q[0], q[1], seed + 17 * j, jag=3, steps=4)
                draw_bolt(f, br, width=1, glow=MB[3], edge=MB[2])
            # 命中闪光
            r = [0, 7, 12, 10][k]
            f.disk(gx, gy, r + 5, MB[3], 0.3)
            f.disk(gx, gy, r, MB[4])
            f.disk(gx, gy, r * 0.55, WHITE)
        else:
            # 余电火花
            rs = rng(60 + k)
            f.disk(gx, gy, 6 if k == 4 else 3, MB[3], 0.45)
            for j in range(12 if k == 4 else 6):
                a = rs.uniform(-3.1, 0.0)
                l = rs.uniform(5, 16) * (1.0 if k == 4 else 0.7)
                p0 = (gx + math.cos(a) * 3, gy + math.sin(a) * 3)
                p1 = (gx + math.cos(a) * l, gy + math.sin(a) * l)
                mid = ((p0[0] + p1[0]) / 2 + rs.uniform(-2, 2), (p0[1] + p1[1]) / 2 + rs.uniform(-2, 2))
                f.line(p0, mid, MB[4])
                f.line(mid, p1, MB[3])
            if k == 4:
                pts = bolt_points(gx + 2, 20, gx, gy, 77, jag=4, steps=9)
                for a, b in zip(pts, pts[1:]):
                    f.line(a, b, MB[3], 0.6)
        out.append(snap_or_glow(f.img()))
    return out, (gx, gy)


def fx_dark():
    """暗魔法：紫黑漩涡 8 帧，60x60。"""
    out = []
    N = 8
    cx, cy = 30, 30
    for k in range(N):
        f = FX(60, 60)
        dx = f.x - cx
        dy = f.y - cy
        r = np.sqrt(dx * dx + dy * dy)
        th = np.arctan2(dy, dx)
        if k == 0:
            rs = rng(3)
            for j in range(14):
                a = rs.uniform(0, 6.28)
                rr = rs.uniform(14, 24)
                f.disk(cx + math.cos(a) * rr, cy + math.sin(a) * rr, 1.3, MD[3], 0.9)
            f.disk(cx, cy, 3, MD[1])
        elif k <= 5:
            R_ = [0, 12, 17, 21, 22, 18][k]
            spin = k * 0.9
            arms = np.sin(th * 3 + r * 0.45 - spin)
            inside = r < R_
            f.put(inside & (r > R_ * 0.25), MD[1], 0.55)
            f.put(inside & (arms > 0.35), MD[2])
            f.put(inside & (arms > 0.7), MD[3])
            f.put(inside & (arms > 0.9) & (r > R_ * 0.4), MD[4])
            core = R_ * (0.32 if k < 5 else 0.5)
            f.disk(cx, cy, core + 1.5, MD[2])
            f.disk(cx, cy, core, MD[0])
            f.disk(cx, cy, core * 0.55, INK)
            # 被吸入的颗粒
            rs = rng(10 + k)
            for j in range(10):
                a = rs.uniform(0, 6.28)
                rr = R_ + rs.uniform(1, 6)
                f.pix(cx + math.cos(a) * rr, cy + math.sin(a) * rr, MD[3 + (j % 2)])
            if k == 5:
                f.ring(cx, cy, R_ - 2, R_, MD[4], 0.7)
        elif k == 6:
            # 爆散的暗色碎片
            f.disk(cx, cy, 10, MD[4], 0.5)
            f.disk(cx, cy, 6, MD[1])
            rs = rng(66)
            for j in range(12):
                a = j / 12 * 6.28 + rs.uniform(-0.2, 0.2)
                l0, l1 = 8, rs.uniform(18, 27)
                f.line((cx + math.cos(a) * l0, cy + math.sin(a) * l0), (cx + math.cos(a) * l1, cy + math.sin(a) * l1),
                       MD[3], 1.0, width=2)
                f.pix(cx + math.cos(a) * l1, cy + math.sin(a) * l1, MD[4])
        else:
            rs = rng(77)
            for j in range(10):
                a = rs.uniform(0, 6.28)
                rr = rs.uniform(10, 24)
                f.disk(cx + math.cos(a) * rr, cy + math.sin(a) * rr - 3, 1.6, MD[2], 0.8)
            f.disk(cx, cy, 4, MD[2], 0.6)
        out.append(snap_or_glow(f.img()))
    return out


def star(f, cx, cy, r, col_out, col_in, alpha=1.0):
    """四角星闪光。"""
    f.line((cx - r, cy), (cx + r, cy), col_out, alpha)
    f.line((cx, cy - r), (cx, cy + r), col_out, alpha)
    if r >= 3:
        f.line((cx - r * 0.45, cy - r * 0.45), (cx + r * 0.45, cy + r * 0.45), col_out, alpha * 0.8)
        f.line((cx - r * 0.45, cy + r * 0.45), (cx + r * 0.45, cy - r * 0.45), col_out, alpha * 0.8)
    f.disk(cx + 0.5, cy + 0.5, max(1.0, r * 0.28), col_in, alpha)


def fx_light():
    """星辉：从天而降的光束 + 星芒，48x96，锚点在命中点 (24, 72)。"""
    out = []
    W_, H_ = 48, 96
    gx, gy = 24, 72
    for k in range(6):
        f = FX(W_, H_)
        if k == 0:
            star(f, gx, 10, 6, GOLD[4], WHITE)
            star(f, gx - 9, 22, 3, GOLD[3], WHITE, 0.8)
            star(f, gx + 10, 16, 3, GOLD[3], WHITE, 0.8)
        else:
            w = [0, 2, 6, 9, 6, 2][k]
            if w:
                f.put((np.abs(f.x - gx) < w + 3) & (f.y < gy + 6), GOLD[4], 0.25)
                f.put((np.abs(f.x - gx) < w) & (f.y < gy + 4), GOLD[4])
                f.put((np.abs(f.x - gx) < max(1, w - 2)) & (f.y < gy + 3), WHITE)
            if k >= 2:
                rr = [0, 0, 9, 14, 12, 7][k]
                f.disk(gx, gy, rr + 4, GOLD[4], 0.3)
                f.disk(gx, gy, rr, GOLD[4])
                f.disk(gx, gy, rr * 0.6, WHITE)
                star(f, gx, gy, rr + 8, WHITE, WHITE)
            rs = rng(30 + k)
            for j in range(5 + k * 2):
                sx = gx + rs.uniform(-20, 20)
                sy = rs.uniform(4, gy + 8)
                s = 1 if j % 3 else 2
                star(f, sx, sy, s + (1 if k in (3, 4) else 0), GOLD[4] if j % 2 else WHITE, WHITE, 0.95)
        out.append(snap_or_glow(f.img()))
    return out, (gx, gy)


def fx_heal():
    """治疗：绿色光柱 + 上升光点，40x72，锚点 (20, 48) = 目标身体中心。"""
    out = []
    W_, H_ = 40, 72
    cx, cy = 20, 48
    ground = 70
    N = 8
    for k in range(N):
        f = FX(W_, H_)
        w = [2, 5, 8, 9, 9, 7, 4, 2][k]
        top = [58, 38, 18, 6, 4, 8, 18, 34][k]
        amp = [0.7, 0.85, 1.0, 1.0, 1.0, 0.85, 0.65, 0.45][k]
        fade = np.clip((f.y - top) / 18.0, 0, 1) * amp
        wav = np.sin(f.y * 0.55 + k * 1.3) * 0.8
        dxa = np.abs(f.x - cx - wav * (w > 4))
        body = (f.y < ground) & (f.y > top - 6)
        f.put(body & (dxa < w + 2.5), HL[2], 0.25 * fade)
        f.put(body & (dxa < w), HL[3], 0.45 * fade)
        f.put(body & (dxa < max(1.0, w * 0.4)), HL[4], 0.7 * fade)
        # 地面光环
        f.ell(cx, ground - 1, w + 7, 2.8, HL[2], 0.55 * amp)
        f.ell(cx, ground - 1, w + 4, 1.8, HL[3], 0.9 * amp)
        f.ell(cx, ground - 1, w + 1, 1.0, HL[4], amp)
        # 上升的光点（十字小星）
        rs = rng(7)
        for j in range(14):
            px = cx + rs.uniform(-15, 15)
            base = rs.uniform(ground - 12, ground)
            sp = rs.uniform(5, 9)
            py = base - sp * k - rs.uniform(0, 6)
            if py < 2 or py > ground - 1:
                continue
            s_ = 1 + (j % 3 == 0)
            f.line((px - s_, py), (px + s_, py), HL[3])
            f.line((px, py - s_), (px, py + s_), HL[3])
            f.pix(px, py, WHITE)
        out.append(snap_or_glow(f.img()))
    return out, (cx, cy)


def fx_hitspark():
    out = []
    for k in range(4):
        f = FX(28, 28)
        cx, cy = 14, 14
        if k == 0:
            f.disk(cx, cy, 5, FIRE[4], 0.5)
            f.disk(cx, cy, 3, WHITE)
        elif k == 1:
            f.disk(cx, cy, 7, FIRE[4], 0.35)
            for j in range(8):
                a = j / 8 * 6.28 + 0.2
                l = 12 if j % 2 == 0 else 7
                f.line((cx + math.cos(a) * 2, cy + math.sin(a) * 2), (cx + math.cos(a) * l, cy + math.sin(a) * l),
                       FIRE[4], 1.0, width=2 if j % 2 == 0 else 1)
            f.disk(cx, cy, 4, WHITE)
        elif k == 2:
            for j in range(8):
                a = j / 8 * 6.28 + 0.2
                l0, l1 = (6, 13) if j % 2 == 0 else (5, 9)
                f.line((cx + math.cos(a) * l0, cy + math.sin(a) * l0), (cx + math.cos(a) * l1, cy + math.sin(a) * l1),
                       FIRE[3])
            f.ring(cx, cy, 4, 6, FIRE[4], 0.8)
        else:
            for j in range(8):
                a = j / 8 * 6.28 + 0.2
                l = 12 if j % 2 == 0 else 9
                f.pix(cx + math.cos(a) * l, cy + math.sin(a) * l, FIRE[3])
            f.ring(cx, cy, 6, 7, FIRE[3], 0.5)
        out.append(snap_or_glow(f.img()))
    return out


def fx_critspark():
    out = []
    for k in range(5):
        f = FX(64, 64)
        cx, cy = 32, 32
        if k == 0:
            f.disk(cx, cy, 14, WHITE, 0.35)
            f.disk(cx, cy, 8, WHITE)
            f.disk(cx, cy, 5, FIRE[4])
        elif k == 1:
            f.disk(cx, cy, 16, FIRE[4], 0.3)
            for j in range(12):
                a = j / 12 * 6.28 + 0.13
                l = 30 if j % 3 == 0 else 20
                f.line((cx + math.cos(a) * 3, cy + math.sin(a) * 3), (cx + math.cos(a) * l, cy + math.sin(a) * l),
                       WHITE, 1.0, width=3 if j % 3 == 0 else 2)
            f.ring(cx, cy, 10, 13, FIRE[4])
            f.disk(cx, cy, 8, WHITE)
        elif k == 2:
            for j in range(12):
                a = j / 12 * 6.28 + 0.13
                l0, l1 = (12, 30) if j % 3 == 0 else (12, 23)
                f.line((cx + math.cos(a) * l0, cy + math.sin(a) * l0), (cx + math.cos(a) * l1, cy + math.sin(a) * l1),
                       FIRE[4], 1.0, width=2 if j % 3 == 0 else 1)
            f.ring(cx, cy, 15, 19, WHITE)
            f.ring(cx, cy, 13, 15, FIRE[3], 0.8)
            f.disk(cx, cy, 6, FIRE[4], 0.6)
        elif k == 3:
            for j in range(12):
                a = j / 12 * 6.28 + 0.13
                l0, l1 = (20, 30) if j % 3 == 0 else (18, 25)
                f.line((cx + math.cos(a) * l0, cy + math.sin(a) * l0), (cx + math.cos(a) * l1, cy + math.sin(a) * l1),
                       FIRE[3])
            f.ring(cx, cy, 21, 24, FIRE[4], 0.9)
        else:
            rs = rng(8)
            for j in range(16):
                a = rs.uniform(0, 6.28)
                l = rs.uniform(22, 30)
                f.pix(cx + math.cos(a) * l, cy + math.sin(a) * l, FIRE[3 + (j % 2)])
            f.ring(cx, cy, 25, 26, FIRE[3], 0.5)
        out.append(snap_or_glow(f.img()))
    return out


def fx_dust():
    out = []
    E = PAL['earth']
    for k in range(3):
        f = FX(28, 14)
        rs = rng(4)
        for j in range(6):
            x = 4 + j * 4 + rs.uniform(-1, 1)
            y = 10 - (j % 2)
            r = [2.0, 3.2, 3.6][k] * (0.8 + 0.4 * (j % 3) / 2)
            yy = y - k * 1.5
            a = [1.0, 0.9, 0.55][k]
            f.disk(x + k * (j - 2.5) * 0.6, yy, r, E[2], a)
            f.disk(x + k * (j - 2.5) * 0.6 - 0.6, yy - 0.8, r * 0.6, E[3], a)
            if k < 2:
                f.pix(x - 1 + k * (j - 2.5) * 0.6, yy - r * 0.5, E[4], a)
        out.append(snap_or_glow(f.img()))
    return out


def fx_slash():
    """刀光：右上→左下的粗新月，40x40。"""
    out = []
    SKY = PAL['cloth_sky']
    for k in range(3):
        f = FX(40, 40)
        cx, cy = 20, 20
        u = np.array([-1.0, 1.0]) / math.sqrt(2)     # 斩击方向（右上→左下）
        v = np.array([1.0, 1.0]) / math.sqrt(2)      # 新月鼓起方向（右下）
        px = f.x - cx
        py = f.y - cy
        sAl = px * u[0] + py * u[1]
        wAl = px * v[0] + py * v[1]
        Lh = [15, 17, 17][k]
        t = np.clip(sAl / Lh, -1, 1)
        inside = np.abs(sAl) < Lh
        bend = 5.0 * (1 - t * t)                        # 中段外凸
        thick = [1.4, 4.2, 2.4][k] * (1 - t * t) ** 0.8
        off = [0.0, 0.0, -1.5][k]
        d = wAl - bend - off
        m = inside & (d > -thick) & (d < 0.6)
        if k == 0:
            f.put(m, WHITE)
        elif k == 1:
            f.put(inside & (d > -thick - 1.2) & (d < 1.2), SKY[3], 0.6)
            f.put(m, SKY[4])
            f.put(m & (d > -thick * 0.45), WHITE)
        else:
            f.put(m, SKY[3], 0.85)
            f.put(m & (d > -thick * 0.4), SKY[4])
            # 断续
            f.put(m & (np.abs(np.sin(sAl * 0.9)) < 0.25), SKY[2], 0.0)
        out.append(snap_or_glow(f.img()))
    return out


# ================================================================ 打包
def generate(assets_dir, prev_dir):
    os.makedirs(prev_dir, exist_ok=True)
    items = []   # (fx_name, [imgs], anchor or None, durations)

    def add(name, imgs, durs, anchor=None):
        if isinstance(durs, int):
            durs = [durs] * len(imgs)
        items.append((name, imgs, anchor, durs))

    add('arrow', fx_arrow(), 1)
    add('javelin', fx_javelin(), 1)
    add('handaxe', fx_handaxe(), 3)
    add('fireball', fx_fireball(), 4)
    add('fire_burst', fx_fire_burst(), [3, 3, 4, 4, 4, 5, 5, 6])
    th, tha = fx_thunder()
    add('thunder', th, [3, 3, 4, 3, 5, 6], tha)
    add('dark', fx_dark(), [4, 4, 4, 4, 5, 4, 5, 6])
    li, lia = fx_light()
    add('light', li, [5, 4, 4, 6, 6, 8], lia)
    he, hea = fx_heal()
    add('heal', he, [4, 4, 5, 6, 6, 5, 5, 6], hea)
    add('hitspark', fx_hitspark(), [2, 3, 3, 4])
    add('critspark', fx_critspark(), [2, 3, 4, 4, 5])
    add('dust', fx_dust(), [4, 5, 6])
    add('slash', fx_slash(), [2, 3, 4])

    # 货架式打包（每行高度 = 行内最高帧），帧间留 1px
    MAXW = 512
    placed = []
    x = y = rowh = 0
    for name, imgs, anchor, durs in items:
        for i, im in enumerate(imgs):
            h, w = im.shape[:2]
            if x + w > MAXW:
                x = 0
                y += rowh + 1
                rowh = 0
            placed.append((name, i, im, x, y, anchor))
            x += w + 1
            rowh = max(rowh, h)
    total_h = y + rowh
    sheet = np.zeros((total_h, MAXW, 4), np.uint8)
    frames = {}
    for name, i, im, px, py, anchor in placed:
        h, w = im.shape[:2]
        sheet[py:py + h, px:px + w] = im
        ax = w // 2
        ay = anchor[1] if anchor is not None else h // 2
        frames['%s%d' % (name, i)] = [px, py, w, h, ax, ay]
    anims = {}
    for name, imgs, anchor, durs in items:
        anims[name] = [['%s%d' % (name, i), int(durs[i])] for i in range(len(imgs))]
    Image.fromarray(sheet, 'RGBA').save(os.path.join(assets_dir, 'battle_fx.png'), optimize=True)
    meta = dict(frames=frames, anims=anims,
                info=dict(facing='left', note=ANCHOR_NOTE,
                          loop=['fireball', 'handaxe'],
                          projectiles=['arrow', 'javelin', 'handaxe', 'fireball']))
    with open(os.path.join(assets_dir, 'battle_fx.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, separators=(',', ':'))
    # 预览：深色底 3 倍
    sc = 3
    bg = Image.new('RGBA', (MAXW, total_h), (28, 30, 44, 255))
    bg.alpha_composite(Image.fromarray(sheet, 'RGBA'))
    bg.resize((MAXW * sc, total_h * sc), Image.NEAREST).save(os.path.join(prev_dir, 'fx_sheet.png'))
    print('battle_fx: %d 帧，图集 %dx%d' % (len(frames), MAXW, total_h))
