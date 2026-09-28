# -*- coding: utf-8 -*-
"""
战斗动画 —— 坐骑：马 / 天马 / 飞龙，以及骑手（复用人形木偶）。
坐骑局部坐标：原点 = 马背鞍座中心，x 向右为后、向左为前，y 向下；pitch>0 前身抬起（人立）。
姿势 pose = {'m': 坐骑姿势, 'r': 骑手姿势（build_human 的键，hip 由鞍座决定，可用 hip_off 微调）}
"""
import math
import numpy as np
from palette import PAL, INK, INK2
from battle_rig import (W, H, AX, AY, Mat, mat, metal, m_cap, m_poly, m_ell, m_line, m_pts, stamp, V, adir,
                        perp, rot, dilate4)
from battle_body import Frame, build_human, P2, glint_post, Z_FLEG

# 深度：远侧翼 < 远侧腿 < 尾 < 身体 < 近侧腿 < 鞍 < 近侧翼 < 骑手(10+)
ZM_WING_F = 0.2
ZM_LEG_F = 0.5
ZM_TAIL = 1.0
ZM_BODY = 2.0
ZM_NECK = 2.2
ZM_HEAD = 2.5
ZM_LEG_N = 2.9
ZM_SADDLE = 3.3
ZM_WING_N = 4.2


def _tf(origin, pitch):
    o = V(*origin)

    def T(x, y):
        return o + rot(V(x, y), pitch)
    return T


# ---------------------------------------------------------------- 马
HORSE = dict(
    barrel=((0.5, 5.2), 12.5, 6.4),
    chest=((-9.5, 4.6), 6.4, 7.0),
    rump=((9.5, 4.2), 7.4, 6.8),
    thigh=((10.0, 8.0), 5.0, 6.4),
    neck=[(-5.0, -1.5), (-12.5, -10.5), (-15.5, -12.8), (-19.0, -11.6), (-19.2, -7.5), (-16.5, 4.0), (-10.0, 6.0)],
    head=[(-15.4, -13.6), (-18.6, -15.0), (-22.0, -12.8), (-27.6, -7.4), (-28.6, -5.2), (-27.4, -3.6),
          (-24.0, -3.6), (-19.2, -6.2), (-16.6, -8.6)],
    ear=[(-15.6, -13.2), (-15.2, -17.8), (-17.6, -14.6)],
    ear2=[(-14.2, -13.0), (-13.6, -17.2), (-15.8, -14.2)],
    eye=(-20.8, -11.4), nostril=(-27.4, -5.8),
    fl_root=(-10.0, 9.5), fr_root=(-7.8, 9.0), hl_root=(9.5, 9.0), hr_root=(11.2, 8.5),
    fleg=(8.0, 7.2, 2.6), hleg=(8.6, 7.4, 2.6),
    tail_root=(16.4, 0.6),
    saddle=(0.5, -1.2), withers=(-5.5, -1.0),
)


def horse_leg(F, T, root, angs, lens, coat, hoof, z, group, bias, front=True, sock=None):
    """三段腿：上臂/前臂(或大腿/小腿) → 管骨 → 系部+蹄。angs 为相对身体的方向角。"""
    p0 = T(*root)
    pitch_fix = 0.0
    a1, a2, a3 = angs
    l1, l2, l3 = lens
    # 方向角在坐骑局部系中定义，需加上身体俯仰
    d1 = rot(adir(a1), F._mpitch)
    d2 = rot(adir(a2), F._mpitch)
    d3 = rot(adir(a3), F._mpitch)
    k = p0 + d1 * l1
    f = k + d2 * l2
    h = f + d3 * l3
    if front:
        F.add(m_cap(p0, k, 2.8, 1.7), coat, z, group, bias=bias, sigma=1.0)
    else:
        F.add(m_cap(p0, k, 3.4, 1.6), coat, z, group, bias=bias, sigma=1.1)
    F.add(m_cap(k, f, 1.45, 1.25), coat, z + 0.1, group, bias=bias)
    if sock is not None:
        F.add(m_cap(k + (f - k) * 0.55, f, 1.5, 1.35), sock, z + 0.15, group, bias=bias)
    F.add(m_cap(f, h, 1.35, 1.5), coat if sock is None else sock, z + 0.2, group, bias=bias)
    # 蹄：沿 d3 方向的梯形
    n3 = perp(d3)
    hp = [h - n3 * 1.7 - d3 * 0.3, h + n3 * 1.7 - d3 * 0.3, h + n3 * 2.1 + d3 * 1.8, h - n3 * 2.4 + d3 * 1.8]
    F.add(m_poly(hp), hoof, z + 0.3, group, level=2)
    return h + d3 * 1.8


def build_horse(M, HL, F):
    """M: 坐骑姿势；HL: 坐骑外观。返回 info（鞍座点、头部点、马镫点等）。"""
    pitch = M.get('pitch', 0.0)
    F._mpitch = pitch
    org = P2(M.get('pos', (0, -33)))
    T = _tf(org, pitch)
    coat = HL['coat']
    mane = HL['mane']
    hoof = HL.get('hoof', mat('iron'))
    sc = HL.get('size', 1.0)

    def TS(x, y):
        return T(x * sc, y * sc)

    info = dict(T=TS, pitch=pitch, origin=org)
    B = HORSE
    # 身体（多个椭圆合成一个部件，统一明暗）
    body = np.zeros((H, W), bool)
    for (c, rx, ry) in (B['barrel'], B['chest'], B['rump']):
        cc = TS(*c)
        body |= m_ell(cc, rx * sc, ry * sc, math.radians(pitch))
    # 后腿肌肉
    tc = TS(*B['thigh'][0])
    thigh = m_ell(tc, B['thigh'][1] * sc, B['thigh'][2] * sc, math.radians(pitch + 10))
    # 颈 + 头（头部可独立转动：绕枕部）
    na = M.get('neck', 0.0)
    npiv = TS(-8.0, 2.0)

    def TN(x, y):
        p = TS(x, y)
        return npiv + rot(p - npiv, na)
    neck_pts = [TN(*p) for p in B['neck']]
    neck = m_poly(neck_pts)
    # 身体+颈+后腿肌肉合成一个剪影，统一明暗（避免木偶感的分段线）
    F.add(body | thigh | neck, coat, ZM_BODY, 'm_body', sigma=2.2)
    # 肌肉/结构暗线
    F.add(m_line(TS(6.0, 6.5), TS(8.0, 11.5)) & (body | thigh), None, ZM_BODY + 0.05, 'm_body', inherit=-1)
    F.add(m_line(TN(-13.0, 3.5), TN(-9.5, 7.5)) & body, None, ZM_BODY + 0.05, 'm_body', inherit=-1)
    ha = M.get('head', 0.0)
    hpiv = TN(-16.5, -11.0)

    def TH(x, y):
        p = TN(x, y)
        return hpiv + rot(p - hpiv, ha)
    F.add(m_poly([TH(*p) for p in B['head']]), coat, ZM_HEAD, 'm_head', sigma=1.1)
    F.add(m_poly([TH(*p) for p in B['ear']]), coat, ZM_HEAD + 0.1, 'm_ear', bias=0.1)
    F.add(m_poly([TH(*p) for p in B['ear2']]), coat, ZM_HEAD - 0.1, 'm_ear2', bias=-0.4)
    eye = TH(*B['eye'])
    F.add(m_pts([(int(eye[0]), int(eye[1]))]), None, ZM_HEAD + 0.3, 'm_eye',
          fixed=np.broadcast_to(np.array(INK, np.uint8), (H, W, 4)).copy(), lines=False, outline=False)
    ns = TH(*B['nostril'])
    F.add(m_pts([(int(ns[0]), int(ns[1]))]), None, ZM_HEAD + 0.3, 'm_eye',
          fixed=np.broadcast_to(np.array(coat.tones[1], np.uint8), (H, W, 4)).copy(), lines=False, outline=False)
    # 鬃毛：沿颈背的一条毛发带 + 额发
    mp = [TN(-5.0, -2.5), TN(-9.0, -7.0), TN(-12.8, -11.6), TN(-15.4, -13.8), TN(-14.2, -10.4), TN(-11.0, -6.2),
          TN(-6.5, -0.4)]
    swing = M.get('mane', 0.0)
    mp2 = [p + V(swing * 0.6, 0) for p in mp]
    F.add(m_poly(mp2), mane, ZM_NECK + 0.3, 'm_mane', sigma=1.0)
    F.add(m_poly([TH(-16.0, -13.8), TH(-19.0, -12.5), TH(-17.4, -11.2)]), mane, ZM_HEAD + 0.2, 'm_fore', level=3)
    # 缰绳/辔头
    if HL.get('bridle'):
        br = HL['bridle']
        F.add(m_line(TH(-17.0, -9.0), TH(-25.5, -5.0)) | m_line(TH(-18.6, -12.6), TH(-18.0, -6.4)), br,
              ZM_HEAD + 0.25, 'm_head', level=2)
    # 尾巴
    ta = M.get('tail', 0.0)
    tr = TS(*B['tail_root'])
    segs = [(-60 + ta, 5.0, 2.4), (-35 + ta * 1.3, 5.5, 2.2), (-15 + ta * 1.6, 5.5, 1.6), (-5 + ta * 1.8, 4.0, 1.0)]
    p = tr
    tm = np.zeros((H, W), bool)
    for i, (a, ln, r) in enumerate(segs):
        d = rot(adir(a), pitch)
        q = p + d * ln * sc
        r1 = segs[i + 1][2] if i + 1 < len(segs) else 0.8
        tm |= m_cap(p, q, r * sc, r1 * sc)
        p = q
    F.add(tm, mane, ZM_TAIL, 'm_tail', sigma=1.1)
    # 四条腿
    fl = B['fleg']
    hl = B['hleg']
    sock = HL.get('sock')
    legs = M.get('legs', {})
    std = dict(nf=(0, 0, 18), ff=(-4, -2, 16), nh=(-22, 8, 16), fh=(-16, 4, 14))
    for key, root, lens, z, g, bias, front in (
            ('ff', B['fr_root'], fl, ZM_LEG_F, 'm_leg_ff', -0.45, True),
            ('fh', B['hr_root'], hl, ZM_LEG_F, 'm_leg_fh', -0.45, False),
            ('nf', B['fl_root'], fl, ZM_LEG_N, 'm_leg_nf', 0.0, True),
            ('nh', B['hl_root'], hl, ZM_LEG_N, 'm_leg_nh', 0.0, False)):
        angs = legs.get(key, std[key])
        horse_leg(F, TS, root, angs, [x * sc for x in lens], coat, hoof, z, g, bias, front, sock)
    # 鞍与鞍布
    if HL.get('cloth') is not None:
        cm = HL['cloth']
        cp = [TS(-6.5, -1.6), TS(6.0, -2.2), TS(8.0, 7.5), TS(3.0, 9.4), TS(-5.5, 9.0), TS(-7.5, 4.0)]
        F.add(m_poly(cp), cm, ZM_SADDLE, 'm_cloth', sigma=1.2)
        if HL.get('cloth_trim') is not None:
            F.add(m_line(TS(8.0, 7.5), TS(3.0, 9.4)) | m_line(TS(3.0, 9.4), TS(-5.5, 9.0)), HL['cloth_trim'],
                  ZM_SADDLE + 0.05, 'm_cloth', inherit=0)
    sm = HL.get('saddle', mat('leather'))
    F.add(m_poly([TS(-5.0, -3.0), TS(-3.4, -4.6), TS(4.0, -3.6), TS(5.4, -1.2), TS(-4.6, -0.6)]), sm,
          ZM_SADDLE + 0.2, 'm_saddle', sigma=0.9)
    info['saddle'] = TS(*B['saddle'])
    info['stirrup'] = TS(-1.5, 11.5)
    info['withers'] = TS(*B['withers'])
    info['head'] = TH(-22.0, -9.0)
    return info


# ---------------------------------------------------------------- 翅膀（天马）
def _unit(v):
    return v / max(1e-6, float(np.linalg.norm(v)))


def wing_parts(F, root, ang, spread, length, wm, z, group, bias=0.0, sc=1.0, fold=30.0):
    """羽翼：root 翼根；ang 臂段方向角（-180 朝上，-90 朝后）；手段再向后折 fold 度。
    后缘是一排向后扫的飞羽（锯齿），spread 控制羽毛长度（扇动时收拢）。"""
    L = length * sc
    d1 = adir(ang)
    wrist = root + d1 * (0.42 * L)
    d2 = adir(ang + fold)
    tip = wrist + d2 * (0.60 * L)
    n1 = perp(d1)
    if n1[1] < 0 and abs(n1[1]) > abs(n1[0]) * 0.3:
        n1 = -n1
    if n1[0] < -0.2:
        n1 = -n1
    K = 7
    feathers = []
    for i in range(K + 1):
        t = i / K                                      # 0 = 翼尖 → 1 = 翼根
        if t < 0.58:
            base = tip + (wrist - tip) * (t / 0.58)
        else:
            base = wrist + (root - wrist) * ((t - 0.58) / 0.42)
        fd = _unit(d2 * (1.0 - t) * 1.1 + n1 * (0.35 + 1.1 * t))
        flen = L * (0.20 + 0.34 * math.sin(math.pi * min(1.0, 0.18 + t * 0.95))) * (0.55 + 0.45 * spread)
        feathers.append(base + fd * flen)
    trail = []
    for i, fp in enumerate(feathers):
        trail.append(fp)
        if i + 1 < len(feathers):
            mid = (fp + feathers[i + 1]) / 2
            # 两根羽毛之间向前缘回缩，形成锯齿
            t = (i + 0.5) / K
            base = tip + (wrist - tip) * min(1.0, t / 0.58) if t < 0.58 else wrist + (root - wrist) * ((t - 0.58) / 0.42)
            trail.append(mid + (base - mid) * 0.22)
    poly = [root, wrist, tip] + trail + [root + n1 * 2.5]
    m = m_poly(poly)
    F.add(m, wm, z, group, sigma=1.5, bias=bias)
    # 覆羽分层：沿前缘内侧一条暗线 + 飞羽间隔线
    inner = [p + (q - p) * 0.38 for p, q in zip([tip, wrist, root], [feathers[0], feathers[4], feathers[-1]])]
    F.add((m_line(inner[0], inner[1]) | m_line(inner[1], inner[2])) & m, wm, z + 0.05, group, inherit=-1)
    for i in (1, 3, 5):
        t = i / K
        base = tip + (wrist - tip) * min(1.0, t / 0.58) if t < 0.58 else wrist + (root - wrist) * ((t - 0.58) / 0.42)
        F.add(m_line(base + (feathers[i] - base) * 0.45, feathers[i]) & m, wm, z + 0.05, group, inherit=-1)
    F.add(m_line(root, wrist) | m_line(wrist, tip), wm, z + 0.06, group, inherit=1)
    return tip


# ---------------------------------------------------------------- 飞龙
def build_wyvern(M, WL, F):
    pitch = M.get('pitch', 0.0)
    F._mpitch = pitch
    org = P2(M.get('pos', (0, -36)))
    sc = WL.get('size', 1.0)
    T0 = _tf(org, pitch)

    def TS(x, y):
        return T0(x * sc, y * sc)
    scale = WL['scale']
    belly = WL['belly']
    wingm = WL['wing']
    horn = WL.get('horn', mat('cloth_white'))
    info = dict(T=TS, pitch=pitch, origin=org)
    # 身体
    body = m_ell(TS(1.0, 4.5), 12.0 * sc, 6.6 * sc, math.radians(pitch)) | \
        m_ell(TS(-7.5, 3.5), 6.5 * sc, 6.2 * sc, math.radians(pitch))
    F.add(body, scale, ZM_BODY, 'w_body', sigma=2.0)
    # 腹甲
    bp = [TS(-11.0, 6.0), TS(-4.0, 10.2), TS(6.0, 10.6), TS(11.0, 8.0), TS(4.0, 8.4), TS(-6.0, 7.6)]
    F.add(m_poly(bp), belly, ZM_BODY + 0.1, 'w_belly', sigma=1.0)
    # 脖子（两段）+ 头
    na = M.get('neck', 0.0)
    n0 = TS(-10.0, 0.0)
    d1 = rot(adir(155 + na), pitch)
    n1 = n0 + d1 * 8.5 * sc
    d2 = rot(adir(125 + na * 1.4), pitch)
    n2 = n1 + d2 * 8.0 * sc
    F.add(m_cap(n0, n1, 4.6 * sc, 3.6 * sc) | m_cap(n1, n2, 3.6 * sc, 3.0 * sc), scale, ZM_NECK, 'w_neck',
          sigma=1.4)
    # 颈下腹鳞
    F.add(m_cap(n0 + perp(d1) * -2.4 * sc, n1 + perp(d1) * -2.0 * sc, 1.4 * sc, 1.2 * sc) |
          m_cap(n1 + perp(d2) * -2.0 * sc, n2 + perp(d2) * -1.6 * sc, 1.2 * sc, 1.0 * sc), belly,
          ZM_NECK + 0.1, 'w_neckb', sigma=0.8)
    ha = M.get('head', 0.0) + pitch
    jaw = M.get('jaw', 0.0)

    def TH(x, y):
        return n2 + rot(V(x * sc, y * sc), ha)
    upper = [TH(1.5, -3.2), TH(-3.0, -3.8), TH(-8.5, -2.0), TH(-11.5, -0.6), TH(-11.0, 0.8), TH(-4.0, 0.8),
             TH(1.8, 1.8)]
    F.add(m_poly(upper), scale, ZM_HEAD, 'w_head', sigma=1.0)
    lower = [TH(-1.0, 1.0), TH(-10.0, 1.2 + jaw * 0.4), TH(-9.6, 2.6 + jaw), TH(-3.0, 3.4 + jaw * 0.3),
             TH(1.4, 2.6)]
    F.add(m_poly(lower), belly if jaw > 0.5 else scale, ZM_HEAD - 0.1, 'w_jaw', sigma=0.9, bias=-0.2)
    if jaw > 0.5:
        # 张嘴：牙齿
        F.add(m_line(TH(-9.5, 1.0), TH(-4.0, 1.2)), None, ZM_HEAD + 0.2, 'w_teeth',
              fixed=np.broadcast_to(np.array(PAL['cloth_white'][4], np.uint8), (H, W, 4)).copy(), lines=False)
    # 角与眼
    F.add(m_poly([TH(0.5, -3.4), TH(5.5, -6.8), TH(2.6, -2.2)]) | m_poly([TH(-2.0, -3.6), TH(2.4, -7.6),
                                                                              TH(-0.4, -3.0)]),
          horn, ZM_HEAD + 0.15, 'w_horn', sigma=0.8, bias=0.1)
    e = TH(-4.4, -1.6)
    F.add(m_pts([(int(e[0]), int(e[1]))]), None, ZM_HEAD + 0.3, 'w_eye',
          fixed=np.broadcast_to(np.array(WL.get('eye', PAL['eye_gold'][3]), np.uint8), (H, W, 4)).copy(),
          lines=False, outline=False)
    info['head'] = TH(-10.5, 0.5)
    info['mouth'] = TH(-11.0, 1.2)
    # 尾巴（四段递细）
    ta = M.get('tail', 0.0)
    p = TS(11.5, 3.0)
    tm = np.zeros((H, W), bool)
    segs = [(-80 + ta, 7.0, 4.2), (-60 + ta * 1.3, 7.0, 3.0), (-45 + ta * 1.6, 6.5, 2.0), (-30 + ta * 2.0, 5.5, 1.2)]
    for i, (a, ln, r) in enumerate(segs):
        d = rot(adir(a), pitch)
        q = p + d * ln * sc
        r1 = segs[i + 1][2] if i + 1 < len(segs) else 0.6
        tm |= m_cap(p, q, r * sc, r1 * sc)
        p = q
    F.add(tm, scale, ZM_TAIL, 'w_tail', sigma=1.3)
    # 尾尖骨刺
    dd = rot(adir(segs[-1][0]), pitch)
    F.add(m_poly([p + perp(dd) * 2.0, p + dd * 3.5, p - perp(dd) * 2.0]), horn, ZM_TAIL + 0.1, 'w_spike', level=3)
    # 后腿（收起：大腿前伸、小腿后折、爪下垂）
    legs = M.get('legs', {})
    for key, root, z, g, bias in (('f', (7.5, 6.0), ZM_LEG_F, 'w_leg_f', -0.45),
                                  ('n', (5.5, 7.0), ZM_LEG_N, 'w_leg_n', 0.0)):
        a1, a2, a3 = legs.get(key, (35, -40, 20))
        p0 = TS(*root)
        k = p0 + rot(adir(a1), pitch) * 7.0 * sc
        f = k + rot(adir(a2), pitch) * 6.0 * sc
        F.add(m_cap(p0, k, 3.6 * sc, 2.4 * sc), scale, z, g, bias=bias, sigma=1.2)
        F.add(m_cap(k, f, 2.0 * sc, 1.5 * sc), scale, z + 0.1, g, bias=bias)
        d3 = rot(adir(a3), pitch)
        cl = [f + perp(d3) * 1.8, f + d3 * 3.8 + perp(d3) * 1.2, f + d3 * 4.4, f + d3 * 3.6 - perp(d3) * 2.4,
              f - perp(d3) * 1.6]
        F.add(m_poly(cl), horn, z + 0.2, g, level=2)
    # 蝠翼：远侧 + 近侧
    wa = M.get('wing', 0.0)   # 扇动：+ 向上，- 向下
    for side, z, bias, off in (('far', ZM_WING_F, -0.5, V(2.5, -1.5)), ('near', ZM_WING_N, 0.0, V(0, 0))):
        root = TS(-7.0, -2.5) + off
        # 臂骨：翼根 -> 腕 -> 指尖（wa: +1 高举 / -1 下拍）
        up_ang = -160 - wa * 35 + (6 if side == 'far' else 0)
        wrist = root + rot(adir(up_ang), pitch) * 15.0 * sc
        fingers = []
        for fa, fl in ((-125 - wa * 25, 15.0), (-100 - wa * 20, 19.0), (-75 - wa * 14, 16.5), (-50 - wa * 8, 12.0)):
            fingers.append(wrist + rot(adir(fa), pitch) * fl * sc)
        back = TS(6.0, 0.5)
        poly = [root, wrist] + fingers + [back]
        # 膜的锯齿：相邻指尖之间向内凹
        mem = [root, wrist]
        for i in range(len(fingers)):
            mem.append(fingers[i])
            nxt = fingers[i + 1] if i + 1 < len(fingers) else back
            mid = (fingers[i] + nxt) / 2
            c = (wrist + root) / 2
            mem.append(mid + (c - mid) * 0.22)
        mem.append(back)
        mm = m_poly(mem)
        F.add(mm, wingm, z, 'w_wing_' + side, sigma=1.4, bias=bias)
        bones = m_cap(root, wrist, 1.3 * sc, 1.0 * sc)
        for fp in fingers:
            bones |= m_line(wrist, fp)
        F.add(bones, scale, z + 0.1, 'w_bone_' + side, bias=bias + 0.1, sigma=0.8)
        F.add(m_poly([wrist + V(-0.5, 0.5), wrist + rot(adir(up_ang + 20), pitch) * 3.5 * sc, wrist + V(1.2, 0.2)]),
              horn, z + 0.15, 'w_claw', level=3)
    info['saddle'] = TS(-1.0, -2.2)
    info['stirrup'] = TS(-2.0, 8.0)
    return info


# ---------------------------------------------------------------- 组合：坐骑 + 骑手
def build_mounted(pose, look, F=None):
    if F is None:
        F = Frame()
    M = pose['m']
    R = dict(pose['r'])
    kind = look['mount']
    ML = look['mount_look']
    if kind == 'wyvern':
        mi = build_wyvern(M, ML, F)
    else:
        mi = build_horse(M, ML, F)
        if kind == 'pegasus':
            pitch = mi['pitch']
            T = mi['T']
            wa = M.get('wing', 0.0)
            spread = M.get('spread', 1.0)
            wm = ML['wing']
            # 远侧翅膀在身后（更高一点），近侧翅膀盖在马身上
            wsz = ML.get('size', 1.0)
            wl = ML.get('wing_len', 34)
            # wa: +1 高举，0 平展向后上方，-1 下拍
            wing_parts(F, T(-6.0 * wsz, -3.2 * wsz), -150 - wa * 32 + pitch, spread, wl * 0.95, wm,
                       ZM_WING_F, 'p_wing_far', bias=-0.5, fold=34 - wa * 10)
            wing_parts(F, T(-6.5 * wsz, 0.5 * wsz), -140 - wa * 32 + pitch, spread, wl, wm,
                       ZM_WING_N, 'p_wing_near', bias=0.05, fold=30 - wa * 10)
    saddle = mi['saddle']
    ho = R.get('hip_off', (0, 0))
    hip = saddle + V(*ho) + V(0, -1.5)
    R['hip'] = (hip[0] - AX, hip[1] - AY)
    st = mi['stirrup'] + V(*R.get('foot_off', (0, 0)))
    R['ff'] = (st[0] - AX, st[1] - AY, R.get('foot_ang', 15))
    R.setdefault('fk', 1.0)
    L2 = dict(look)
    L2['no_back_leg'] = True
    # 天马：近侧翅膀盖住骑手的腿（腿画在翅膀之下、马身之上）
    L2['front_leg_z'] = (ZM_WING_N - 0.3) if kind == 'pegasus' else 40
    F2, info = build_human(R, L2, F)
    info['mount'] = mi
    return F2, info
