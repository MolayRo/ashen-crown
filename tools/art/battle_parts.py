# -*- coding: utf-8 -*-
"""
战斗动画 —— 附加部件：弓/箭、魔法书、长袍、盾、箭筒、围巾、兜帽、毛皮披肩等。
"""
import math
import numpy as np
from palette import PAL, INK, INK2
from battle_rig import (W, H, Mat, mat, metal, m_cap, m_poly, m_ell, m_line, m_pts, stamp, V, adir, perp, rot,
                        dilate4)
from battle_body import Z_CAPE_B, Z_BARM, Z_TORSO, Z_SKIRT, Z_NECK, Z_HEAD, Z_FARM, Z_SHIELD


def solid(c):
    return np.broadcast_to(np.array(c, np.uint8), (H, W, 4)).copy()


# ---------------------------------------------------------------- 弓 / 箭
def bow_parts(F, hand, aim, draw, arrow, spec, z, string_z=None):
    d = adir(aim)
    n = perp(d)
    h = V(*hand)
    half = spec.get('half', 11.0)
    curve = spec.get('curve', 3.2)
    wood = spec.get('wood', mat('wood'))
    k = 11
    pts = []
    for i in range(k):
        t = -1 + 2 * i / (k - 1)
        bend = curve * (t * t)
        if draw is not None:
            bend *= 1.35
        pts.append(h + n * (t * half) + d * (0.9 * (1 - t * t)) - d * bend)
    m = np.zeros((H, W), bool)
    for i in range(k - 1):
        r = 1.05 if abs(i - (k - 2) / 2) < 2.5 else 0.8
        m |= m_cap(pts[i], pts[i + 1], r)
    F.add(m, wood, z, 'bow', sigma=0.8, bias=0.1)
    F.add(m_cap(h - n * 1.4, h + n * 1.4, 1.1), spec.get('grip', mat('leather')), z + 0.1, 'bow', level=3)
    tip0, tip1 = pts[0], pts[-1]
    strc = PAL['cloth_white'][2]
    if draw is not None:
        dp = V(*draw)
        sm = m_line(tip0, dp) | m_line(tip1, dp)
    else:
        dp = None
        sm = m_line(tip0, tip1)
    sz = string_z if string_z is not None else z + 30
    F.add(sm & ~m, None, sz, 'string', fixed=solid(strc), outline=False, lines=False, cast=False)
    info = dict(tip=h + d * 2, tips=(tip0, tip1))
    if arrow:
        start = dp if dp is not None else h - d * 9
        head = h + d * 5.5
        arrow_parts(F, start, head, sz + 0.5, spec.get('fletch'))
        info['arrow_tip'] = head
    return info


def arrow_parts(F, tail, head, z, fletch=None):
    tail = V(*tail)
    head = V(*head)
    dd = head - tail
    L = float(np.linalg.norm(dd))
    d = dd / max(1e-6, L)
    n = perp(d)
    shaft = m_line(tail, head - d * 1.5)
    F.add(shaft, mat('wood'), z, 'arrow', level=4, lines=False, cast=False)
    tip = m_poly([head + d * 1.8, head - d * 1.8 + n * 1.5, head - d * 1.0, head - d * 1.8 - n * 1.5])
    F.add(tip | m_line(head - d * 1.5, head + d * 1.5), metal('steel'), z + 0.1, 'arrow', level=4, lines=False)
    fl = fletch or PAL['cloth_white'][3]
    fm = m_line(tail + d * 0.5 + n * 1.0, tail + d * 3.0) | m_line(tail + d * 0.5 - n * 1.0, tail + d * 3.0)
    F.add(fm, None, z + 0.05, 'arrow', fixed=solid(fl), lines=False)


# ---------------------------------------------------------------- 魔法书
def book_parts(F, hand, ang, spec, z, open_=False):
    d = adir(ang)
    n = perp(d)
    h = V(*hand)
    cover = spec.get('cover', mat('cloth_crimson'))
    page = mat('cloth_white')
    if not open_:
        c = h + d * 1.5
        pts = [c + d * 3.5 + n * 2.8, c + d * 3.5 - n * 2.8, c - d * 3.2 - n * 2.8, c - d * 3.2 + n * 2.8]
        F.add(m_poly(pts), cover, z, 'book', sigma=0.9, bias=0.1)
        F.add(m_line(c + d * 3.0 - n * 2.4, c - d * 2.7 - n * 2.4), page, z + 0.1, 'book', level=3)
        F.add(m_cap(c + d * 0.2 + n * 0.3, c + d * 0.2 + n * 0.3, 1.0), spec.get('gem', metal('gold')), z + 0.2,
              'book', level=4)
        info = dict(tip=c + d * 4)
    else:
        # 摊开的书：正对观众的两页 + 下方露出封面厚度 + 书脊，固定朝向便于辨认
        c = h + V(-0.5, -3.2)
        lp = [c + V(-5.2, -0.8), c + V(-0.4, -2.6), c + V(-0.4, 2.0), c + V(-5.2, 2.8)]
        rp = [c + V(0.4, -2.6), c + V(5.2, -0.8), c + V(5.2, 2.8), c + V(0.4, 2.0)]
        cov = [c + V(-6.0, -0.6), c + V(0.0, -2.2), c + V(6.0, -0.6), c + V(6.0, 3.9), c + V(0.0, 3.2),
               c + V(-6.0, 3.9)]
        F.add(m_poly(cov), cover, z, 'book', level=2)
        F.add(m_poly(lp), page, z + 0.1, 'bookp', level=4, lines=False)
        F.add(m_poly(rp), page, z + 0.1, 'bookp', level=3, lines=False)
        F.add(m_line(c + V(0, -2.4), c + V(0, 2.8)), cover, z + 0.2, 'bookp', level=1, lines=False)
        for yy in (-0.6, 1.0):
            F.add(m_line(c + V(-4.2, yy + 0.2), c + V(-1.6, yy - 0.6)) | m_line(c + V(1.6, yy - 0.6), c + V(4.2, yy + 0.2)),
                  page, z + 0.15, 'bookp', level=2, lines=False)
        info = dict(tip=c + V(0, -4))
    return info


# ---------------------------------------------------------------- 长袍
def robe_fn(m, top=2.5, flare=2.2, z=Z_SKIRT, hem=None, folds=True, group='robe', lift=0.0):
    """长袍下摆：覆盖双腿到脚踝。"""
    def fn(F, P, L, info):
        T = info['T']
        legs = info['legs']
        (hpf, kf, af, _) = legs['f']
        (hpb, kb, ab, _) = legs.get('b', legs['f'])
        wf = T(4.0, top)
        wb = T(-4.3, top)
        hem_f = af + V(-flare - 1.5, -1.2 - lift)
        hem_b = ab + V(flare + 2.0, -1.2 - lift)
        mid_f = kf + V(-2.8, 0)
        mid_b = kb + V(3.0, 0)
        sway = P.get('cape', 0.0) * 0.3
        bot = V((hem_f[0] + hem_b[0]) / 2, max(hem_f[1], hem_b[1]) + 0.8)
        pts = [wf, mid_f, hem_f, bot, hem_b + V(sway, 0), mid_b + V(sway * 0.5, 0), wb]
        F.add(m_poly(pts), m, z, group, sigma=1.4)
        if folds:
            for t in (0.3, 0.62):
                a = wf + (wb - wf) * t + V(0, 2.5)
                b = hem_f + (hem_b - hem_f) * (t * 0.9 + 0.05) + V(0, -1.0)
                F.add(m_line(a, b), m, z + 0.05, group, inherit=-1)
        if hem is not None:
            F.add(m_line(hem_f + V(0.5, 0.2), bot + V(0, -0.2)) | m_line(bot + V(0, -0.2), hem_b + V(sway - 0.5, 0.2)),
                  hem, z + 0.06, group, inherit=0)
    return fn


# ---------------------------------------------------------------- 盾
SHIELDS = {
    'kite': [(-4.6, -7.0), (4.6, -7.0), (4.8, -1.0), (2.6, 5.0), (0.0, 9.0), (-2.6, 5.0), (-4.8, -1.0)],
    'tower': [(-5.0, -9.5), (-2.6, -11.0), (2.6, -11.0), (5.0, -9.5), (5.2, 7.5), (0.0, 10.5), (-5.2, 7.5)],
    'heater': [(-5.2, -6.5), (5.2, -6.5), (5.0, 0.5), (2.8, 5.0), (0.0, 7.0), (-2.8, 5.0), (-5.0, 0.5)],
}


def shield_fn(sm, shape='kite', size=1.0, z=Z_SHIELD, rim=None, emblem=None, arm='f', offset=(0, 0), squash=0.72):
    def fn(F, P, L, info):
        shp, elbow, wrist, hand = info['arms'][arm]
        c = elbow + (wrist - elbow) * 0.5 + V(*offset) + V(*P.get('shield_off', (0, 0)))
        tilt = P.get('shield_tilt', 0)
        if shape == 'round':
            m = m_ell(c, 6.0 * size * squash, 6.6 * size, math.radians(tilt))
        else:
            pts = [c + rot(V(x * size * squash, y * size), tilt) for (x, y) in SHIELDS[shape]]
            m = m_poly(pts)
        inner = m & ~dilate4(~m)
        F.add(m, sm, z, 'shield', sigma=1.6, bias=0.05)
        if rim is not None:
            F.add(m & ~inner, rim, z + 0.1, 'shield', inherit=1)
        if emblem is not None:
            emblem(F, c, z + 0.2, P)
        info['shield_c'] = c
    return fn


# ---------------------------------------------------------------- 背部/颈部附件
def quiver_fn(qm, z=Z_CAPE_B + 1, fletch=None):
    def fn(F, P, L, info):
        T = info['T']
        a = T(-3.8, 12.5)
        b = T(-5.2, 1.5)
        F.add(m_cap(a, b, 2.2, 1.8), qm, z, 'quiver', sigma=1.0)
        fl = fletch or PAL['cloth_white'][3]
        up = info['up']
        for k, off in enumerate((-1.2, 0.4, 1.8)):
            p0 = a + V(off, 0)
            p1 = p0 + up * 3.2 + V(-0.4 * k, 0)
            F.add(m_line(p0, p1), None, z - 0.1, 'quiverf', fixed=solid(fl if k != 1 else PAL['team_red'][3]))
    return fn


def scarf_fn(sm, z_front=Z_HEAD + 1, tail_len=9.0):
    """围巾：颈部一圈 + 身后飘带（随 cape 飘动）。"""
    def fn(F, P, L, info):
        T = info['T']
        sway = P.get('cape', 0.0)
        n0 = T(2.6, 13.3)
        n1 = T(-3.0, 13.6)
        F.add(m_cap(n0, n1, 2.0, 2.2), sm, z_front, 'scarf', sigma=1.0)
        root = T(-3.4, 12.5)
        e1 = root + V(4.0 + sway * 0.8, 3.0 + tail_len * 0.35 - sway * 0.5)
        e2 = root + V(6.0 + sway * 1.3, tail_len - sway * 0.8)
        F.add(m_cap(root, e1, 1.9, 1.6) | m_cap(e1, e2, 1.6, 1.2), sm, Z_CAPE_B + 0.5, 'scarf_t', sigma=1.0, bias=-0.1)
    return fn


def hood_down_fn(hm, z=Z_NECK - 1):
    def fn(F, P, L, info):
        T = info['T']
        c = T(-2.4, 14.2)
        F.add(m_ell(c, 4.2, 2.8, 0.2), hm, z, 'hood', sigma=1.2)
    return fn


def mantle_fn(mm, z=Z_HEAD + 2, size=1.0, group='mantle', shag=True):
    """肩部毛皮披肩/斗篷领。"""
    def fn(F, P, L, info):
        T = info['T']
        pts = [T(4.6 * size, 11.5), T(2.5, 14.8), T(-3.0, 15.2), T(-5.8 * size, 12.5), T(-6.0 * size, 9.0),
               T(-2.0, 10.2), T(2.0, 9.6)]
        F.add(m_poly(pts), mm, z, group, sigma=1.2, bias=0.1)
        if shag:
            e = [T(4.6 * size, 11.5), T(2.0, 9.6), T(-2.0, 10.2), T(-6.0 * size, 9.0)]
            for i in range(len(e) - 1):
                a, b = e[i], e[i + 1]
                for t in (0.25, 0.75):
                    p = a + (b - a) * t
                    F.add(m_line(p, p + info['up'] * -1.6 + V(0.6, 0)), mm, z + 0.05, group, inherit=0)
    return fn


# ---------------------------------------------------------------- 会飘动的头发/头纱
def ponytail_fn(hm, root=(4.0, -7.0), segs=((-30, 4.0, 2.2), (-15, 4.5, 1.9), (-5, 4.0, 1.4)), z=Z_HEAD - 0.5,
                swing=1.0, tie=None):
    """马尾：root 相对颈部顶端（头部锚点）；segs=(方向角, 长度, 半径)。方向角 0=下，-90=后。
    pose['cape'] 越大（向前冲）马尾越向后扬。"""
    def fn(F, P, L, info):
        hpos = info['head']
        sway = P.get('cape', 0.0) * swing + P.get('hair', 0.0)
        p = hpos + V(*root)
        m = np.zeros((H, W), bool)
        ang_acc = 0.0
        for i, (a, ln, r) in enumerate(segs):
            ang = a - sway * (6.0 + 3.0 * i)
            d = adir(ang)
            q = p + d * ln
            r1 = segs[i + 1][2] if i + 1 < len(segs) else r * 0.6
            m |= m_cap(p, q, r, r1)
            p = q
        F.add(m, hm, z, 'ponytail', sigma=1.0, bias=0.05)
        if tie is not None:
            F.add(m_ell(hpos + V(*root) + V(0.3, 0.3), 1.2, 1.2), tie, z + 0.1, 'tie', level=3)
    return fn


def veil_fn(vm, top=(2.5, -9.0), z=Z_NECK - 0.5, length=13.0):
    """修女头纱：从头顶后部垂到背上，随动作飘。"""
    def fn(F, P, L, info):
        hpos = info['head']
        sway = P.get('cape', 0.0)
        a = hpos + V(*top)
        pts = [a + V(-1.5, 0), a + V(3.2, 0.5), a + V(5.2 + sway * 0.5, length * 0.6),
               a + V(4.0 + sway * 1.0, length), a + V(0.5 + sway * 0.6, length - 1.0), a + V(-1.0, 6.0)]
        F.add(m_poly(pts), vm, z, 'veil', sigma=1.2, bias=-0.05)
    return fn


def longhair_fn(hm, top=(3.0, -6.0), z=Z_NECK - 0.6, length=11.0, width=4.0):
    """披肩长发（头后垂下）。"""
    def fn(F, P, L, info):
        hpos = info['head']
        sway = P.get('cape', 0.0) + P.get('hair', 0.0)
        a = hpos + V(*top)
        pts = [a + V(-1.0, 0), a + V(width * 0.7, 0.2), a + V(width + sway * 0.5, length * 0.55),
               a + V(width * 0.8 + sway * 1.0, length), a + V(width * 0.2 + sway * 0.8, length - 1.5),
               a + V(-0.5 + sway * 0.3, length * 0.6)]
        F.add(m_poly(pts), hm, z, 'longhair', sigma=1.1, bias=0.0)
        # 发丝暗线
        F.add(m_line(a + V(width * 0.35, 1.0), a + V(width * 0.5 + sway * 0.8, length - 1.0)), hm, z + 0.05,
              'longhair', inherit=-1)
    return fn
