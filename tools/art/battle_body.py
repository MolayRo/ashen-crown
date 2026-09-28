# -*- coding: utf-8 -*-
"""
战斗动画 —— 人形木偶与武器。
姿势(pose)参数（锚点为原点，x 向右为“后”，向左为“前”，y 向下）：
  hip=(x,y) 骨盆；lean 躯干前倾角；ff/bf=(x,y[,脚角]) 前/后脚踝；fk/bk 膝盖弯向(+1 前)
  fh/bh=(dx,dy) 前/后手相对各自肩膀；fe/be 肘弯向；wa 武器方向角；wh 持武器的手('f'/'b')
  wz 武器深度覆盖；cape 披风飘动；head=(dx,dy) 头部偏移；smear=(a0,a1) 挥砍拖影
"""
import math
import numpy as np
from palette import PAL, INK, INK2
from battle_rig import (W, H, AX, AY, Part, Mat, mat, metal, m_cap, m_poly, m_ell, m_line, m_pts,
                        line_pts, stamp, V, adir, ang_of, perp, ik2, rot, dilate4, shift, m_arc)

# 深度层
Z_CAPE_B = 5
Z_BLEG = 10
Z_BARM = 20
Z_WEAP_B = 24
Z_TORSO = 30
Z_FLEG = 40
Z_SKIRT = 45
Z_NECK = 48
Z_HEAD = 50
Z_PAULD = 55
Z_WEAP_F = 60
Z_FARM = 70
Z_SHIELD = 80


def P2(p):
    """锚点坐标 -> 画布坐标"""
    return V(AX + p[0], AY + p[1])


class Frame:
    """一帧的部件收集器"""

    def __init__(self):
        self.parts = []
        self.post = []

    def add(self, mask, m=None, z=0, group=None, **kw):
        p = Part(mask, m, z, group, **kw)
        self.parts.append(p)
        return p


# ---------------------------------------------------------------- 武器
def weapon_parts(F, kind, hand, ang, spec, z, grp='weapon'):
    """在手的位置画武器。ang: 刃/杆指向的方向角。返回有用的点（刃尖等）。"""
    d = adir(ang)
    n = perp(d)
    # 朝光一侧的法向
    lit_n = n if (n[0] * -0.6 + n[1] * -0.8) > 0 else -n
    info = {}
    h = V(*hand)
    if kind in ('sword', 'greatsword', 'dagger'):
        blen = spec.get('len', 20)
        bw = spec.get('bw', 2)
        grip = spec.get('grip', 3)
        guard = spec.get('guard', 2.5)
        steel = spec.get('blade', metal('steel'))
        hilt = spec.get('hilt', metal('gold'))
        gripm = spec.get('gripm', mat('leather'))
        tip = h + d * (2.2 + blen)
        base = h + d * 2.2
        # 刃：两条平行线（亮边/暗边），大剑三条
        e1 = line_pts(base, tip)
        m_edge = m_pts(e1)
        step = V(0, 1) if abs(d[0]) >= abs(d[1]) else V(1, 0)
        if (step[0] * lit_n[0] + step[1] * lit_n[1]) > 0:
            step = -step
        # step 指向背光侧
        m_dark = m_pts([(x + int(step[0]), y + int(step[1])) for (x, y) in e1[:-1]])
        blade = m_edge | m_dark
        lvl = np.full((H, W), 3, np.int16)
        lvl[m_edge] = 5
        lvl[m_dark & ~m_edge] = 3
        if bw >= 3:
            m_d2 = m_pts([(x + 2 * int(step[0]), y + 2 * int(step[1])) for (x, y) in e1[:-2]])
            lvl[m_d2 & ~blade] = 2 if bw == 3 else 3
            blade |= m_d2
            # 血槽
            fl = m_pts([(x + int(step[0]), y + int(step[1])) for (x, y) in e1[2:-4]])
            lvl[fl & m_dark] = 4
        if bw >= 4:
            m_d3 = m_pts([(x + 3 * int(step[0]), y + 3 * int(step[1])) for (x, y) in e1[:-3]])
            lvl[m_d3 & ~blade] = 2
            blade |= m_d3
            fl2 = m_pts([(x + 2 * int(step[0]), y + 2 * int(step[1])) for (x, y) in e1[3:-5]])
            lvl[fl2] = 1
        F.add(blade, steel, z, grp, level=lvl, sigma=1.0)
        # 护手
        gw = spec.get('guard_w', 2.6)
        g0 = h + d * 1.2 - n * gw
        g1 = h + d * 1.2 + n * gw
        F.add(m_cap(g0, g1, 1.0), hilt, z + 0.2, grp, bias=0.1)
        # 握柄
        F.add(m_line(h - d * (grip - 0.5), h + d * 0.8), gripm, z + 0.1, grp, level=2)
        F.add(m_cap(h - d * (grip + 0.2), h - d * (grip + 0.2), 1.0), hilt, z + 0.15, grp, level=4)
        info['tip'] = tip
        info['base'] = base
    elif kind in ('lance', 'javelin'):
        L0 = spec.get('back', 12)
        L1 = spec.get('len', 24)
        wood = spec.get('shaft', mat('wood'))
        head = spec.get('head', metal('steel'))
        p0 = h - d * L0
        p1 = h + d * L1
        e1 = line_pts(p0, p1)
        m1 = m_pts(e1)
        step = V(0, 1) if abs(d[0]) >= abs(d[1]) else V(1, 0)
        if (step[0] * lit_n[0] + step[1] * lit_n[1]) > 0:
            step = -step
        m2 = m_pts([(x + int(step[0]), y + int(step[1])) for (x, y) in e1])
        lvl = np.full((H, W), 3, np.int16)
        lvl[m1] = 4
        lvl[m2 & ~m1] = 2
        F.add(m1 | m2, wood, z, grp, level=lvl)
        # 枪头（叶形）
        hl = spec.get('head_len', 7)
        hw = spec.get('head_w', 1.9)
        a = p1 - d * 0.5
        b = p1 + d * hl
        mid = p1 + d * (hl * 0.35)
        pts = [a, mid + n * hw, b, mid - n * hw]
        hm = m_poly(pts) | m_line(a, b)
        F.add(hm, head, z + 0.3, grp, sigma=0.8, bias=0.15)
        # 枪头根部的金属箍
        F.add(m_cap(p1 - d * 1.2, p1 - d * 0.2, 1.2), spec.get('ring', metal('iron')), z + 0.2, grp, level=3)
        if spec.get('tassel'):
            tm = spec['tassel']
            F.add(m_cap(p1 - d * 1.5 + n * 1.2, p1 - d * 3.5 + n * 2.6, 1.0, 0.7), tm, z + 0.1, grp + '_t', bias=0.1)
        info['tip'] = b
        info['base'] = p0
    elif kind == 'axe':
        L0 = spec.get('back', 4)
        L1 = spec.get('len', 15)
        wood = spec.get('shaft', mat('wood'))
        head = spec.get('head', metal('steel'))
        p0 = h - d * L0
        p1 = h + d * L1
        e1 = line_pts(p0, p1)
        m1 = m_pts(e1)
        step = V(0, 1) if abs(d[0]) >= abs(d[1]) else V(1, 0)
        if (step[0] * lit_n[0] + step[1] * lit_n[1]) > 0:
            step = -step
        m2 = m_pts([(x + int(step[0]), y + int(step[1])) for (x, y) in e1])
        lvl = np.full((H, W), 3, np.int16)
        lvl[m1] = 4
        lvl[m2 & ~m1] = 2
        F.add(m1 | m2, wood, z, grp, level=lvl)
        # 斧头：刃朝 side 方向（默认 n 的反向 = 刃朝挥砍方向）
        side = spec.get('side', -1)
        s = n * side
        hs = spec.get('head_size', 1.0)
        c = p1 - d * (3.0 * hs)
        pts = [c + d * (3.4 * hs) + s * 0.5,
               c + d * (5.8 * hs) + s * (5.5 * hs),
               c + d * (2.0 * hs) + s * (7.8 * hs),
               c - d * (1.8 * hs) + s * (7.8 * hs),
               c - d * (4.8 * hs) + s * (5.2 * hs),
               c - d * (2.2 * hs) + s * 0.5]
        hm = m_poly(pts)
        F.add(hm, head, z + 0.3, grp, sigma=1.0, bias=0.1)
        # 刃口亮线
        edge = m_line(c + d * (5.4 * hs) + s * (5.6 * hs), c - d * (4.3 * hs) + s * (5.6 * hs)) & hm
        F.add(edge, head, z + 0.35, grp, level=4)
        # 背刺
        if spec.get('spike', True):
            F.add(m_poly([c + d * 1.4 - s * 0.3, c - s * (3.2 * hs), c - d * 1.6 - s * 0.3]), head, z + 0.25, grp, bias=0.0)
        info['tip'] = c + s * (7.8 * hs)
        info['base'] = p0
    elif kind == 'staff':
        L0 = spec.get('back', 12)
        L1 = spec.get('len', 14)
        shaft = spec.get('shaft', mat('wood'))
        p0 = h - d * L0
        p1 = h + d * L1
        e1 = line_pts(p0, p1)
        m1 = m_pts(e1)
        step = V(0, 1) if abs(d[0]) >= abs(d[1]) else V(1, 0)
        if (step[0] * lit_n[0] + step[1] * lit_n[1]) > 0:
            step = -step
        m2 = m_pts([(x + int(step[0]), y + int(step[1])) for (x, y) in e1])
        lvl = np.full((H, W), 3, np.int16)
        lvl[m1] = 4
        lvl[m2 & ~m1] = 2
        F.add(m1 | m2, shaft, z, grp, level=lvl)
        orn = spec.get('orn', metal('gold'))
        top = p1 + d * 3.0
        # 环形杖头
        ring_r = spec.get('ring', 2.8)
        rm = m_ell(top + d * 0.5, ring_r + 0.9, ring_r + 0.9) & ~m_ell(top + d * 0.5, ring_r - 0.6, ring_r - 0.6)
        F.add(rm, orn, z + 0.3, grp, sigma=0.8, bias=0.1)
        gem = spec.get('gem')
        if gem is not None:
            F.add(m_ell(top + d * 0.5, 1.3, 1.3), gem, z + 0.4, grp + '_g', bias=0.3, sigma=0.7)
        F.add(m_cap(p1 - d * 0.5, p1 + d * 0.8, 1.3), orn, z + 0.35, grp, level=3)
        info['tip'] = top + d * 0.5
        info['base'] = p0
    elif kind == 'handaxe':
        return weapon_parts(F, 'axe', hand, ang, dict(spec, len=7, back=2, head_size=0.62, spike=False), z, grp)
    elif kind == 'stick':
        L0 = spec.get('back', 3)
        L1 = spec.get('len', 20)
        p0 = h - d * L0
        p1 = h + d * L1
        e1 = line_pts(p0, p1)
        m1 = m_pts(e1)
        F.add(m1, spec.get('shaft', mat('wood')), z, grp, level=3)
        F.add(m_cap(p1, p1, 1.3), spec.get('shaft', mat('wood')), z + 0.1, grp, level=4)
        info['tip'] = p1
        info['base'] = p0
    return info


# ---------------------------------------------------------------- 人形
DEF_BODY = dict(
    torso_len=13.0, thigh=11.2, shin=10.8, uarm=7.0, farm=6.4, ankle=2.4,
    thigh_r=(2.8, 2.2), shin_r=(2.2, 1.6), uarm_r=(2.1, 1.8), farm_r=(1.8, 1.5), hand_r=1.6,
    torso=[(3.6, 0.5), (-3.7, 0.5), (-4.3, 5.0), (-5.0, 9.6), (-4.2, 12.9), (0.4, 13.9),
           (4.2, 12.8), (5.3, 9.4), (4.3, 5.0)],
    fsh=(-1.0, 11.4), bsh=(1.8, 11.8), neck=(0.5, 13.2), fhip=(0.9, 0.0), bhip=(-0.7, 0.3),
)

FOOT = [(1.7, -1.6), (1.7, 2.4), (-4.2, 2.4), (-4.2, 1.1), (-2.3, 0.0), (-0.5, -1.8)]


def smear_post(F, hand, a0, a1, r0, r1, width=1.3, taper=0.85, style='steel', mode='under'):
    """武器拖影：从角度 a0 扫到 a1（刃在 hand 周围 r0~r1 的环带）。"""
    hand = V(*hand)
    n = max(10, int(abs(a1 - a0) / 5))
    tmap = np.full((H, W), -1.0)
    dist = np.sqrt((np.arange(W)[None, :] + 0.5 - hand[0]) ** 2 + (np.arange(H)[:, None] + 0.5 - hand[1]) ** 2)
    for i in range(n + 1):
        t = i / n
        a = a0 + (a1 - a0) * t
        d = adir(a)
        rin = r1 - (r1 - r0) * (t ** taper if t > 0 else 0)
        rin = max(r0, min(r1 - 2.0, rin))
        m = m_cap(hand + d * rin, hand + d * r1, width)
        tmap[m] = np.maximum(tmap[m], t)
    mask = tmap >= 0
    pal = {
        'steel': [PAL['cloth_sky'][2], PAL['cloth_sky'][3], PAL['cloth_sky'][4], PAL['grey'][5]],
        'gold': [PAL['fire'][2], PAL['fire'][3], PAL['fire'][4], PAL['grey'][5]],
        'dark': [PAL['magic_dark'][2], PAL['magic_dark'][3], PAL['magic_dark'][4], PAL['grey'][5]],
        'red': [PAL['team_red'][3], PAL['team_red'][4], PAL['team_red'][5], PAL['grey'][5]],
    }[style]
    col = np.zeros((H, W, 4), np.uint8)
    rim = dist > (r1 - 2.2)
    col[mask] = pal[0]
    col[mask & (tmap > 0.3)] = pal[1]
    col[mask & (tmap > 0.55)] = pal[2]
    col[mask & (tmap > 0.8)] = pal[3]
    col[mask & rim & (tmap > 0.15)] = pal[2]
    col[mask & rim & (tmap > 0.45)] = pal[3]
    F.post.append((mask, col, mode))


GLINT = [
    "...w...",
    "...w...",
    "..wYw..",
    "wwYWYww",
    "..wYw..",
    "...w...",
    "...w...",
]
GLINT_S = [
    ".w.",
    "wWw",
    ".w.",
]


def glint_post(F, pos, big=True):
    lg = {'w': PAL['fire'][4], 'Y': PAL['grey'][5], 'W': PAL['grey'][5]}
    rows = GLINT if big else GLINT_S
    c = len(rows) // 2
    m, col = stamp(rows, lg, pos, (c, c))
    F.post.append((m, col, 'over'))


def build_human(P, L, F=None):
    """P: 姿势；L: 外观。返回 Frame。"""
    if F is None:
        F = Frame()
    B = dict(DEF_BODY)
    B.update(L.get('body', {}))
    sc = L.get('scale', 1.0)
    hip = P2(P.get('hip', (0, -21)))
    lean = math.radians(P.get('lean', 6))
    up = V(-math.sin(lean), -math.cos(lean))
    fwd = V(-math.cos(lean), math.sin(lean))

    def T(a, b):
        return hip + fwd * (a * sc) + up * (b * sc)

    tl = B['torso_len']
    info = {}
    # ---------------- 腿
    legs = {}
    for side, key, kk, zb in (('f', 'ff', 'fk', Z_FLEG), ('b', 'bf', 'bk', Z_BLEG)):
        if side == 'b' and L.get('no_back_leg'):
            continue
        if side == 'f' and L.get('front_leg_z') is not None:
            zb = L['front_leg_z']
        hp = T(*B['fhip' if side == 'f' else 'bhip'])
        ft = P.get(key, (-6, -B['ankle']) if side == 'f' else (6, -B['ankle']))
        ankle_t = P2((ft[0], ft[1]))
        fa = ft[2] if len(ft) > 2 else 0.0
        knee, ankle = ik2(hp, ankle_t, B['thigh'] * sc, B['shin'] * sc, P.get(kk, 1.0))
        legs[side] = (hp, knee, ankle, fa)
        g = 'leg_' + side
        bias = 0.0 if side == 'f' else L.get('back_bias', -0.35)
        pants = L['pants']
        boots = L.get('boots', pants)
        tr = B['thigh_r']
        sr = B['shin_r']
        F.add(m_cap(hp, knee, tr[0] * sc, tr[1] * sc), pants, zb, g, bias=bias)
        F.add(m_cap(knee, ankle, sr[0] * sc, sr[1] * sc), pants, zb + 0.1, g, bias=bias)
        bt = L.get('boot_top', 0.45)
        if boots is not pants and bt > 0:
            bp = knee + (ankle - knee) * (1 - bt)
            F.add(m_cap(bp, ankle, (sr[1] + 0.55) * sc, (sr[1] + 0.35) * sc), boots, zb + 0.2, g, bias=bias)
            if L.get('boot_cuff'):
                cm = L['boot_cuff']
                dd = (ankle - knee) / max(1e-6, np.linalg.norm(ankle - knee))
                F.add(m_cap(bp - perp(dd) * (sr[1] + 0.6), bp + perp(dd) * (sr[1] + 0.6), 0.9), cm, zb + 0.25, g, bias=bias)
        # 脚
        pts = [ankle + rot(V(x * sc, y * sc), -fa) for (x, y) in L.get('foot', FOOT)]
        F.add(m_poly(pts), boots, zb + 0.3, g, bias=bias - 0.1)
        if L.get('knee_pad'):
            F.add(m_ell(knee + V(-0.6, 0), 2.2 * sc, 2.0 * sc), L['knee_pad'], zb + 0.4, g + 'k', bias=bias + 0.1)
    info['legs'] = legs

    # ---------------- 躯干
    tpts = [T(a, b) for (a, b) in B['torso']]
    tunic = L['tunic']
    F.add(m_poly(tpts), tunic, Z_TORSO, 'torso', sigma=1.3)
    neckb = T(*B['neck'])
    fsh = T(B['fsh'][0] + P.get('fsh_fwd', 0.0), B['fsh'][1])
    bsh = T(*B['bsh'])
    info.update(hip=hip, up=up, fwd=fwd, T=T, neck=neckb, fsh=fsh, bsh=bsh)

    # ---------------- 头
    neck_top = neckb + up * (2.4 * sc)
    F.add(m_cap(neckb, neck_top, 1.8 * sc, 1.6 * sc), L['skin'], Z_NECK, 'head', bias=-0.4)
    hoff = P.get('head', (0, 0))
    hpos = neck_top + V(*hoff)
    info['head'] = hpos
    headfn = L['head']
    headfn(F, P, L, hpos, info)

    # ---------------- 手臂
    arms = {}
    for side, key, ek, zb, shp in (('f', 'fh', 'fe', Z_FARM, fsh), ('b', 'bh', 'be', Z_BARM, bsh)):
        hd = P.get(key, (-2, 12) if side == 'f' else (2, 12))
        target = shp + V(hd[0], hd[1])
        if side == 'b' and P.get('two_hand') and P.get('wa') is not None:
            # 双手握持：后手握在前手后方 two_hand 像素处
            d2 = adir(P['wa'])
            target = arms['f'][3] - d2 * P['two_hand'] - d2 * 0.9
        elbow, wrist = ik2(shp, target, B['uarm'] * sc, B['farm'] * sc, P.get(ek, -1.0))
        arms[side] = (shp, elbow, wrist)
        g = 'arm_' + side
        bias = 0.0 if side == 'f' else L.get('back_bias', -0.35)
        zz = P.get('z' + key, zb)
        if side == 'f' and P.get('arm_behind_head'):
            zz = Z_HEAD - 1.5
        if side == 'b' and P.get('back_arm_front'):
            zz = Z_TORSO + 6
        ur = B['uarm_r']
        fr = B['farm_r']
        sleeve = L.get('sleeve', tunic)
        F.add(m_cap(shp, elbow, ur[0] * sc, ur[1] * sc), sleeve, zz, g, bias=bias)
        fore = L.get('forearm', sleeve)
        fl = L.get('sleeve_flare', 0.0)
        F.add(m_cap(elbow, wrist, fr[0] * sc, (fr[1] + fl) * sc), fore, zz + 0.1, g, bias=bias)
        if L.get('bracer'):
            dd = (wrist - elbow)
            F.add(m_cap(elbow + dd * 0.45, wrist, (fr[1] + 0.45) * sc), L['bracer'], zz + 0.15, g, bias=bias)
        hand = wrist + (wrist - elbow) / max(1e-6, np.linalg.norm(wrist - elbow)) * 0.9 * sc
        F.add(m_ell(hand, B['hand_r'] * sc, B['hand_r'] * sc), L.get('glove', L['skin']), zz + 0.3, g, bias=bias + 0.1,
              sigma=0.8)
        arms[side] = (shp, elbow, wrist, hand)
    info['arms'] = arms

    # ---------------- 武器
    wk = L.get('weapon')
    if P.get('wpn'):
        wk = L.get('alt', {}).get(P['wpn'], wk)
    if wk and wk['kind'] in ('bow', 'book') and P.get('wa') is not None:
        import battle_parts as BP
        if wk['kind'] == 'bow':
            # 右手弓手面朝左：近侧(前)手持弓伸向敌人，远侧(后)手拉弦到脸颊（被头部遮住一部分，脸不被挡）
            bow_hand = arms['f'][3]
            draw_hand = arms['b'][3] if P.get('drawn') else None
            winfo = BP.bow_parts(F, bow_hand, P['wa'], draw_hand, P.get('arrow', False), wk,
                                 P.get('wz', Z_WEAP_F), string_z=Z_HEAD - 1.0)
            info['whand'] = bow_hand
        else:
            wh = P.get('wh', wk.get('hand', 'b'))
            hand = arms[wh][3]
            winfo = BP.book_parts(F, hand, P['wa'], wk, P.get('wz', (Z_FARM + 1) if wh == 'f' else (Z_TORSO + 4)),
                                  open_=P.get('book_open', False))
            info['whand'] = hand
        info['weapon'] = winfo
        if P.get('arrow_glint') and winfo.get('arrow_tip') is not None:
            glint_post(F, winfo['arrow_tip'], big=True)
        wk = None
    if wk and P.get('wa') is not None:
        wh = P.get('wh', wk.get('hand', 'f'))
        hand = arms[wh][3]
        base_z = (Z_WEAP_F if wh == 'f' else Z_WEAP_B)
        wz = P.get('wz', base_z)
        winfo = weapon_parts(F, wk['kind'], hand, P['wa'], wk, wz)
        info['weapon'] = winfo
        info['whand'] = hand
        if P.get('smear'):
            a0, a1 = P['smear'][:2]
            r1 = 2.2 + wk.get('len', 20) + (wk.get('head_len', 0) if wk['kind'] in ('lance', 'axe') else 0)
            if wk['kind'] == 'axe':
                r1 = wk.get('len', 15) + 4
            r0 = max(3.0, r1 * 0.5)
            smear_post(F, hand, a0, a1, r0, r1, width=P['smear'][2] if len(P['smear']) > 2 else 1.3,
                       style=wk.get('smear', 'steel'))
        if P.get('thrust'):
            thrust_post(F, winfo['tip'], P['wa'], P['thrust'], wk.get('smear', 'steel'))
        if P.get('glint'):
            glint_post(F, winfo['tip'], big=P['glint'] != 'small')
    # 副手武器（双短剑等）
    wk2 = L.get('weapon2')
    if wk2 and P.get('wa2') is not None:
        wh2 = 'b' if P.get('wh', 'f') == 'f' else 'f'
        hand2 = arms[wh2][3]
        wz2 = P.get('wz2', Z_WEAP_B if wh2 == 'b' else Z_WEAP_F)
        winfo2 = weapon_parts(F, wk2['kind'], hand2, P['wa2'], wk2, wz2, grp='weapon2')
        info['weapon2'] = winfo2
        if P.get('smear2'):
            a0, a1 = P['smear2'][:2]
            r1 = 2.2 + wk2.get('len', 12)
            smear_post(F, hand2, a0, a1, max(3.0, r1 * 0.45), r1, width=1.3, style=wk2.get('smear', 'steel'))
        if P.get('glint2'):
            glint_post(F, winfo2['tip'], big=False)
    if P.get('spark'):
        # 施法手上的光点
        sp = P['spark']
        glint_post(F, arms['f'][3] + V(-2.5, -0.5), big=(sp == 'big'))
    for fn in L.get('torso_extra', []):
        fn(F, P, L, info)
    for fn in L.get('extra', []):
        fn(F, P, L, info)
    return F, info


def thrust_post(F, tip, ang, length, style='steel'):
    """突刺速度线：沿武器方向在枪尖后方画几条平行亮线。"""
    d = adir(ang)
    n = perp(d)
    pal = [PAL['cloth_sky'][3], PAL['cloth_sky'][4], PAL['grey'][5]]
    mask = np.zeros((H, W), bool)
    col = np.zeros((H, W, 4), np.uint8)
    tip = V(*tip)
    for off, l0, l1, c in ((0, 3, length, 2), (-3, 6, length * 0.7, 1), (3, 5, length * 0.8, 1), (-6, 9, length * 0.45, 0),
                           (6, 8, length * 0.5, 0)):
        a = tip - d * l0 + n * off
        b = tip - d * l1 + n * off
        m = m_line(a, b)
        mask |= m
        col[m] = pal[c]
    F.post.append((mask, col, 'under'))


# ---------------------------------------------------------------- 常用附件
def cape_fn(cm, lining=None, length=9.0, width=1.0, z=Z_CAPE_B, collar=None, folds=True, hem=None):
    """披风：挂在肩背，下摆随 pose['cape'] 向后飘；length = 下摆低于骨盆的距离。"""
    def fn(F, P, L, info):
        T = info['T']
        sway = P.get('cape', 0.0)
        lift = P.get('cape_lift', 0.0)
        hip = info['hip']
        bx, by = hip[0], hip[1]
        ln = length - lift
        top_f = T(1.0, 13.6)
        top_b = T(-3.2, 13.2)
        sh_b = T(-5.0, 10.4)
        mid_b = V(bx + 5.2 * width + sway * 0.45, by - 3.0 - lift * 0.3)
        low_b = V(bx + 7.6 * width + sway * 1.0, by + ln - 0.5)
        low_m = V(bx + 3.8 * width + sway * 0.75, by + ln + 1.0)
        low_f = V(bx + 0.2 + sway * 0.45, by + ln - 0.2)
        pts = [top_f, top_b, sh_b, mid_b, low_b,
               V((low_b[0] + low_m[0]) / 2 + 0.2, low_b[1] + 1.4),
               low_m, V((low_m[0] + low_f[0]) / 2, low_m[1] - 0.8), low_f,
               V(bx - 1.0, by - 2.0), T(1.4, 6.0)]
        F.add(m_poly(pts), cm, z, 'cape', sigma=1.5, bias=-0.05)
        if folds:
            # 两道褶皱（深色）
            for (a, b, t) in ((T(-3.4, 10.0), 0.55, 0.9), (T(-1.4, 7.0), 0.35, 0.75)):
                end = low_b + (low_f - low_b) * b
                end = V(end[0], end[1] - 1.0)
                F.add(m_line(a, a + (end - a) * t), cm, z + 0.05, 'cape', inherit=-1)
        if hem is not None:
            F.add(m_line(low_b + V(-0.5, 0.2), low_m) | m_line(low_m, low_f), hem, z + 0.06, 'cape', inherit=0)
        if lining is not None and sway > 2.0:
            # 飘起时露出内衬（下摆内侧）
            lpts = [mid_b + V(-0.8, 1.5), low_b, V(low_b[0] - 1.8, low_b[1] - 0.2),
                    V(mid_b[0] - 1.6, mid_b[1] + 3.0)]
            F.add(m_poly(lpts), lining, z + 0.1, 'cape', level=3)
        if collar is not None:
            F.add(m_cap(T(1.4, 13.3), T(-2.8, 13.0), 1.2), collar, Z_TORSO + 3, 'collar', bias=0.1)
    return fn


def pauldron_fn(pm, size=1.0, z=Z_PAULD):
    def fn(F, P, L, info):
        shp, elbow = info['arms']['f'][0], info['arms']['f'][1]
        d = elbow - shp
        dn = d / max(1e-6, np.linalg.norm(d))
        c = shp + dn * 1.2 * size + V(0.3, -0.2)
        F.add(m_ell(c, 3.0 * size, 2.5 * size, math.atan2(dn[1], dn[0])), pm, z, 'pauld', sigma=1.0, bias=0.05)
    return fn


def poly_local(pts_local, m, z, group, **kw):
    """在躯干局部坐标系下画多边形。"""
    def fn(F, P, L, info):
        T = info['T']
        F.add(m_poly([T(a, b) for (a, b) in pts_local]), m, z, group, **kw)
    return fn


def band_local(a0, b0, a1, b1, r, m, z, group, **kw):
    def fn(F, P, L, info):
        T = info['T']
        F.add(m_cap(T(a0, b0), T(a1, b1), r), m, z, group, **kw)
    return fn


def skirt_fn(m, length=7.0, flare=1.6, z=Z_SKIRT, front_open=False, group='skirt', lining=None, top=2.5):
    """腰下的衣摆：从腰带往下，前后张开。"""
    def fn(F, P, L, info):
        T = info['T']
        legs = info['legs']
        hip = info['hip']
        # 依据两膝位置让衣摆张开
        kf = legs['f'][1]
        kb = legs['b'][1] if 'b' in legs else legs['f'][1] + V(5.0, 0)
        lf = T(4.0, top)
        lb = T(-4.2, top)
        bot = hip[1] + length
        fx = min(lf[0] - 0.5, (kf[0] + hip[0]) / 2 - flare)
        bx = max(lb[0] + 0.5, (kb[0] + hip[0]) / 2 + flare + 1.0)
        sway = P.get('cape', 0.0) * 0.25
        pts = [lf, lb, V(bx + sway, bot - 0.5), V((bx + fx) / 2 + sway * 0.5, bot + 0.5), V(fx, bot - 0.8)]
        F.add(m_poly(pts), m, z, group, sigma=1.2)
        if lining is not None:
            F.add(m_line(V(fx + 0.5, bot - 1.5), lf + V(0.3, 1.0)), lining, z + 0.1, group, level=4)
    return fn


def belt_fn(m, buckle=None, a0=4.3, a1=-4.4, b=2.0, r=1.1, z=Z_SKIRT + 1):
    def fn(F, P, L, info):
        T = info['T']
        F.add(m_cap(T(a0, b), T(a1, b), r), m, z, 'belt', sigma=0.9)
        if buckle is not None:
            F.add(m_cap(T(a0 - 0.8, b), T(a0 - 0.8, b), 1.2), buckle, z + 0.1, 'buckle', level=4)
    return fn


# ---------------------------------------------------------------- 头部模板
def legend_for(L, extra=None):
    sk = L['skin'].tones
    hr = L['hair'].tones
    ey = PAL[L.get('eye', 'eye_blue')]
    lg = {
        'O': INK, 'o': INK2,
        'J': hr[0], 'j': hr[1], 'h': hr[2], 'H': hr[3], 'k': hr[4],
        'Z': sk[0], 'z': sk[1], 's': sk[2], 'S': sk[3], 't': sk[4],
        'e': ey[0], 'E': ey[2], 'F': ey[3],
        'w': PAL['cloth_white'][4], 'W': PAL['cloth_white'][3],
    }
    if extra:
        lg.update(extra)
    return lg


def head_tmpl(rows, anchor, extra=None, z=Z_HEAD, group='head', variants=None):
    """rows: 模板；anchor: 模板中对准颈部顶端的点。extra: 额外字符 -> 颜色（或 lambda L: 颜色）。"""
    def fn(F, P, L, hpos, info):
        lg_extra = {}
        if extra:
            for k, v in extra.items():
                lg_extra[k] = v(L) if callable(v) else v
        lg = legend_for(L, lg_extra)
        r = rows
        hv = P.get('hv')
        if variants and hv in variants:
            r = variants[hv]
        elif hv == 'hurt':
            # 自动闭眼：瞳孔/虹膜 -> 皮肤暗线
            r = [row.replace('E', 'z').replace('e', 'Z').replace('F', 's') for row in rows]
        m, c = stamp(r, lg, hpos, anchor)
        F.add(m, None, z, group, fixed=c, line_color=L['hair'].tones[0])
        info['head_mask'] = m
    return fn
