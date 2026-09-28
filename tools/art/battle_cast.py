# -*- coding: utf-8 -*-
"""
战斗动画 —— 角色外观(look)与动作关键帧(anims)。
每个 set = look（外观：材质、头部模板、附件）+ 动作原型（剑/枪/斧/弓/魔法/杖/…）。
配色严格按 docs/design.md §2；敌军为黑鹰（深红+黑铁），诺德兰为冷色毛皮。
"""
import math
import numpy as np
from palette import PAL, INK, INK2
from battle_rig import Mat, mat, metal, stamp, V, m_cap, m_poly, m_line, m_ell
from battle_body import *
import battle_parts as BP


def P(base=None, **kw):
    d = dict(base or {})
    d.update(kw)
    return d


def skin_mat(name='skin'):
    return Mat(name, hi=0.45, sh=-0.32)


def dark_of(name, shift=1):
    r = PAL[name]
    idx = [0] + [max(0, min(4, i - shift)) for i in range(1, 5)]
    return Mat(None, tones=[r[i] for i in idx])


def custom(tones, **kw):
    return Mat(None, tones=tones, **kw)


CW = PAL['cloth_white']
CR = PAL['cloth_crimson']
BK = PAL['cloth_black']
IR = PAL['iron']
ST = PAL['steel']
GD = PAL['gold']
LE = PAL['leather']

# 瓦尔德：黑发夹灰丝
HAIR_VALDER = custom([BK[0], BK[2], BK[3], PAL['hair_grey'][1], PAL['hair_grey'][3]])

# ============================================================ 头部模板（面朝左，锚点 = 颈部顶端）
HEADS = {}
HEADS['elwin'] = ([
    "....k...h...",
    "..kkkH.hH...",
    ".kkkHHHhHh..",
    "kkHHHHhHHhj.",
    ".kHHHhHHHhhj",
    "kHHHhHHHhhhj",
    ".HhSHHHhhhjj",
    ".hSxtSHShjj.",
    ".SSSSSsShj..",
    ".SeSSSssj...",
    "SSESSssz....",
    ".SSSssz.....",
    "..zssz......",
], (6, 11), {'x': PAL['skin'][1]})
HEADS['glenn'] = ([
    "...kkkHH....",
    "..kHHHHHhh..",
    ".kHHHHHHHhh.",
    ".HHHhHHHhhj.",
    ".hHhhHHhhhj.",
    ".SStSShHhhj.",
    ".jjjSSsHhj..",
    ".SeSzsShhj..",
    "SSESSssShj..",
    ".kHHSsHHj...",
    ".HHHhHHhj...",
    ".kHHHHhj....",
    "..HHHhj.....",
    "...hhj......",
], (6, 10), {})
HEADS['nora'] = ([
    "....kkHH....",
    "..kkHHHHhh..",
    ".kHHHHHHHhh.",
    "kHHHkHHHHhhj",
    ".HHHHHhHhhjj",
    "kHHHhHHhHhj.",
    ".HhSSHhHhhj.",
    ".hSSSShShj..",
    ".SeSSSsShj..",
    "SSESsSsj....",
    ".SSSSsz.....",
    "..zssz......",
], (6, 10), {})
HEADS['serin'] = ([
    "...wwwwW....",
    "..wwwwwWWW..",
    ".wwwwwWWWWV.",
    ".wwHHHHWWWVV",
    "wHHkHHHhWWVV",
    ".HHSSHHhhWVV",
    ".HSSSShHhWVV",
    ".SeSSSsHhWVV",
    "SSESSssHhVV.",
    ".SSSSsHhhVV.",
    "..zSsshHhVV.",
    "...ss.hhjVV.",
], (6, 10), {'w': CW[4], 'W': CW[3], 'V': CW[2]})
HEADS['doran'] = ([
    "...iiIII....",
    "..iIIIIIu...",
    ".iIIIIIIuu..",
    ".iIIIIIIIuU.",
    "iIIIIIIIIuU.",
    "uuuuuuIIuuU.",
    ".SSSSSuIuU..",
    ".SeSSSsIuU..",
    "SxESSsuIuU..",
    ".SSSSssIuU..",
    ".dSSsdsIU...",
    "..dddsIU....",
], (6, 10), {'I': IR[3], 'i': IR[4], 'u': IR[2], 'U': IR[1], 'x': PAL['skin'][1], 'd': PAL['skin'][2]})
HEADS['sid'] = ([
    "..k...k.h...",
    ".kkH.kHhHh..",
    "kkHHHHHHHhh.",
    ".kHHkHHHhHhj",
    "kHHHHHhHHhhj",
    ".HHkHHHhhhj.",
    "hHSSHHhHhjj.",
    ".SSSSSShhj..",
    ".SeSSSsShj..",
    "SSESSSsj....",
    ".ZwSSsz.....",
    "..zssz......",
], (6, 10), {})
HEADS['mira'] = ([
    "....kkHH....",
    "..kkHHHHHh..",
    ".kHHHHHHHhh.",
    "kHHkHHHHHhhj",
    "kHHHHHhHHhhj",
    "HHHHHHhHhhhj",
    "HhSSSHhHhhj.",
    ".SgggShHhj..",
    ".SeSgshHhj..",
    "SSEwgshHhj..",
    ".SSSSsHHh...",
    "..zssHHhj...",
    ".....Hhj....",
], (6, 10), {'g': GD[1]})
HEADS['vera'] = ([
    "....kkkH....",
    "..kkHHHHHh..",
    ".kHHHHHHHwW.",
    "kHHkHHHHwwWc",
    ".HHHHHHhHwWc",
    ".HHHHhHHhhc.",
    ".HhSSHHhhj..",
    ".hSSSSSshj..",
    ".SeSSSsShj..",
    "SSESSSssj...",
    ".SSSSssz....",
    "..zssz......",
], (6, 10), {'w': CW[4], 'W': CW[3], 'c': PAL['cloth_sky'][3]})
_helm_iron = {'I': IR[3], 'i': IR[4], 'u': IR[2], 'U': IR[1], 'O': IR[0]}
_helm_steel = {'I': ST[3], 'i': ST[4], 'u': ST[2], 'U': ST[1], 'O': ST[0]}
_red = {'r': CR[4], 'R': CR[3], 'q': CR[2], 'Q': CR[1]}
_blk = {'b': BK[4], 'B': BK[3], 'n': BK[2], 'N': BK[1]}
HEADS['soldier'] = ([
    ".....iII....",
    "...iiIIIu...",
    "..iIIIIIIu..",
    ".iIIIIIIIuU.",
    "rRRRRRRRRRRq",
    ".SSuSSSuuU..",
    ".SeuSSsSuU..",
    "SSEuSssSU...",
    ".SSSSsssU...",
    "..zsssz.....",
], (6, 8), dict(_helm_iron, **_red))
HEADS['fighter'] = ([
    "....rrRR....",
    "..rrRRRRRq..",
    ".rRRRRRRRqq.",
    "rRRRrRRRRqqH",
    ".qqqqqqRRqHh",
    ".SSSSSSqHhHQ",
    ".jjSSSsSHhhQ",
    ".SeSSSsShh..",
    "SSESSssSh...",
    ".SSdSsdd....",
    "..dddd......",
], (6, 9), dict(_red, d=PAL['skin_dk'][2]))
HEADS['mercenary'] = ([
    "...kkHH..h..",
    "..kHHHHHhHh.",
    ".kHHHHHHHhhj",
    "kHHHkHHHhhhj",
    "rRRRRRRRRqhj",
    ".HhSSSShHhhj",
    ".jjSSSsShhj.",
    ".SeSSSsShj..",
    "SSESSssShj..",
    ".SSSSssj....",
    "..zsssz.....",
], (6, 9), _red)
HEADS['archer'] = ([
    "....llLL....",
    "..llLLLLLm..",
    ".lLLLLLLLmm.",
    ".LLLLLLLLmmM",
    "iIIIIIIIIIuU",
    ".HhSSSShHhj.",
    ".jjSSSsShhj.",
    ".SeSSSsShj..",
    "SSESSssShj..",
    ".SSSSssj....",
    "..zsssz.....",
], (6, 9), dict(_helm_iron, l=LE[4], L=LE[3], m=LE[2], M=LE[1]))
HEADS['mage_e'] = ([
    "....rrRR....",
    "..rrRRRRRq..",
    ".rRRRRRRRqq.",
    "rRRRRRRRRqqQ",
    "rRRhHHHRRqqQ",
    ".RHSSSHhRqQQ",
    ".RSSSSShRqQ.",
    ".qSeSSsSRqQ.",
    "SSSESssRqQ..",
    ".SSSSsRqQ...",
    "..zssRqQ....",
], (6, 9), _red)
HEADS['darkmage'] = ([
    "....bbBB....",
    "..bbBBBBBn..",
    ".bBBBBBBBnn.",
    "bBBBBBBBBnnN",
    "bBBNNNNNBnnN",
    ".BNNQQNNBnNN",
    ".BNyQNNNBnN.",
    ".BSSQQNNBnN.",
    "BSSSSsNBnN..",
    ".BSSssBnN...",
    "..BzsBnN....",
], (6, 9), dict(_blk, Q=CR[1], y=PAL['eye_red'][3]))
HEADS['knight_e'] = ([
    "...iiIII.rR.",
    "..iIIIIIuRq.",
    ".iIIIIIIIuq.",
    "iIIIIIIIIuU.",
    "iIIIIIIIIuU.",
    "OOOOOOIIIuU.",
    "iIIIIIIIIuU.",
    "iOOOOOIIuUU.",
    "iIIIIIIIuU..",
    ".iIIIIIuUU..",
    "..uuuuUU....",
], (6, 9), dict(_helm_iron, **_red))
HEADS['cavalier_e'] = ([
    ".......rRq..",
    "...iiIIRRq..",
    "..iIIIIIRq..",
    ".iIIIIIIIuU.",
    "iIIIIIIIIuU.",
    "OOOOOOOIIuU.",
    ".SSSSSuIuU..",
    ".SeSSsuIuU..",
    "SSESSsuIU...",
    ".SSSSsuIU...",
    "..zssuuU....",
], (6, 9), dict(_helm_iron, **_red))
HEADS['priest'] = ([
    "....bbBB....",
    "..bbBBBBBn..",
    ".bBBBBBBBnn.",
    ".BBBBBBBnnN.",
    "gGGGGGGGGGg.",
    ".SSSSSShhj..",
    ".jjSSSsShj..",
    ".SeSSsSShj..",
    "SSESSssShj..",
    ".SSSSssj....",
    "..zsssz.....",
], (6, 9), dict(_blk, g=GD[4], G=GD[3]))
HEADS['general'] = ([
    "g.........g.",
    "gg.iiIII.gG.",
    ".GgiIIIIuGG.",
    "..iIIIIIIu..",
    ".iIIrrrrIuU.",
    "iIIIIIIIIuU.",
    "OOOOOOOIIuU.",
    "iIIIIIIIIuU.",
    "iOOOOOIIuUU.",
    "iIIIIIIIuU..",
    ".uIIIIIuUU..",
    "..uuuuUU....",
], (6, 10), dict(_helm_iron, g=GD[3], G=GD[2], **_red))
HEADS['gord'] = ([
    "....ttSS....",
    "..tSSSSSs...",
    ".tSSSSSSss..",
    ".SSSSSSSssz.",
    "tSSxSSSSssz.",
    ".jjjSSSsSsz.",
    ".SeSSSssSz..",
    "SSESSsSSsz..",
    ".kHHSsHHz...",
    "kHHHHHHHh...",
    ".HHHHHHhh...",
    ".kHHHHHhj...",
    "..HHHhhj....",
    "...Hhj......",
], (6, 9), {'x': PAL['skin'][1]})
HEADS['hagen'] = ([
    "...iiIII....",
    "..iIIIIIu...",
    ".iIIIIIIuu..",
    "OiIIIIIIIuU.",
    "OOiIIIIIIuU.",
    ".OOOiIIIIuU.",
    ".SSSSSuIuU..",
    ".jjjSSsIuU..",
    ".SeSSssIuU..",
    "SSESSsSIuU..",
    "kkkHSsSIU...",
    ".HkSSssIU...",
    "..zSsszU....",
], (6, 11), _helm_iron)
HEADS['morgan'] = ([
    "....bbBB....",
    "..bbBBBBBn..",
    ".bBBBBBBBnn.",
    "bBBBBBBBBnnN",
    "bBBrrRRRBnnN",
    ".BrSSSSRBnNN",
    ".BSzzSsRBnN.",
    ".rSyzSsSBnN.",
    "SSSSSssBnN..",
    ".SSZSsBnN...",
    "..zsBnN.....",
], (6, 9), dict(_blk, r=CR[3], R=CR[2], y=PAL['eye_red'][2]))
HEADS['grimm'] = ([
    "g..........g",
    "gg..iiII..gG",
    ".Gg.iIIIIgG.",
    "..GiIIIIIuG.",
    "..iIIIIIIIu.",
    ".iIIIIIIIIuU",
    ".uuuuuIIIuUU",
    ".SSSSSsIuU..",
    ".SeSSssIuU..",
    "SSESSsSIuU..",
    ".kHHSsHIU...",
    ".HHHHHHh....",
    "..HkHHh.....",
    "..HhHh......",
    "...Hh.......",
], (6, 10), dict(_helm_steel, g=CW[4], G=CW[2]))
HEADS['valder'] = ([
    ".....kHH....",
    "...kkHHHHh..",
    "..kHHHHHHhh.",
    ".kHHHkHHhhhj",
    "kHHHHHkHHhhj",
    ".SHHHHHkHhhj",
    ".SSSSSSHhhj.",
    ".jjSSSsShhj.",
    ".SeSSsSShj..",
    "SSESSxsShj..",
    ".SSSSssj....",
    ".hHSssz.....",
    "..hHh.......",
], (6, 11), {'x': PAL['skin'][1]})
HEADS['martha'] = ([
    "....wwWW....",
    "..wwWWWWWV..",
    ".wwWWWWWWVV.",
    "wWWWWWWWWVVH",
    "wWWVVVVWWVHH",
    ".VkHHSSVVHHh",
    ".kSSSSsVVHh.",
    ".SSzSSsSV...",
    ".SeSSssSV...",
    "SSESsSsS....",
    ".SSSSsz.....",
    "..zssz......",
], (6, 10), {'w': PAL['cloth_brown'][4], 'W': PAL['cloth_brown'][3], 'V': PAL['cloth_brown'][2]})
HEADS['pegasus_e'] = ([
    "....iiII..w.",
    "..iiIIIIuwW.",
    ".iIIIIIIuWc.",
    "iIIIIIIIIuc.",
    "iIIIIIIIIuU.",
    "uuuIIIIuuuU.",
    ".HhSSSuIuU..",
    ".SSSSSsIuU..",
    ".SeSSSsIu...",
    "SSESSssIU...",
    ".SSSSsz.....",
    "..zssz......",
], (6, 10), dict(_helm_steel, w=CW[4], W=CW[3], c=PAL['cloth_sky'][2]))
HEADS['wyvern'] = ([
    "....iiII....",
    "..iiIIIIu...",
    ".iIIIIIIuu..",
    "iIIIIIIIIuU.",
    "iIIIIIIIIuUU",
    "OOOOOIIIuuUU",
    ".SSSSSuIuUU.",
    ".SeSSsuIuU..",
    "SSESSsuIU...",
    ".SSSSsuIU...",
    "..zssuuU....",
], (6, 9), _helm_steel)


def head(name, variants=None):
    rows, anc, extra = HEADS[name]
    return head_tmpl(rows, anc, extra=extra, variants=variants)


# ============================================================ 徽记
EAGLE_S = ["b...b", "bb.bb", ".bbb.", "..b.."]
EAGLE_L = ["b..b..b", "bb.b.bb", ".bbbbb.", "..bbb..", "..b.b.."]
SCRATCH = ["bx..b", "bbxbb", ".bbx.", "..bx."]
DEER = ["y.y.y", ".yyy.", "..y..", ".yyy.", "..y.."]


def emblem_fn(rows, colors, where=(1.8, 8.4), z=Z_TORSO + 2, group='torso_em'):
    """在躯干局部坐标 where 处盖一个小徽记。"""
    def fn(F, P, L, info):
        pos = info['T'](*where)
        cx = len(rows[0]) // 2
        m, col = stamp(rows, colors, pos, (cx, len(rows) // 2))
        F.add(m, None, z, group, fixed=col, lines=False, cast=False, outline=False)
    return fn


def shield_emblem(rows, colors):
    def fn(F, c, z, P):
        cx = len(rows[0]) // 2
        m, col = stamp(rows, colors, c + V(0, -1), (cx, len(rows) // 2))
        F.add(m, None, z, 'shield_em', fixed=col, lines=False, cast=False, outline=False)
    return fn


# ============================================================ 体型
BODY_F = dict(
    torso=[(3.2, 0.5), (-3.3, 0.5), (-3.8, 5.0), (-4.4, 9.4), (-3.7, 12.6), (0.4, 13.5), (3.7, 12.4), (4.8, 9.3),
           (3.8, 5.0)],
    uarm_r=(1.8, 1.5), farm_r=(1.6, 1.3), thigh_r=(2.6, 2.0), shin_r=(2.0, 1.4), hand_r=1.4,
    fsh=(-0.8, 11.2), bsh=(1.5, 11.6),
)
BODY_BIG = dict(
    torso=[(4.4, 0.5), (-4.5, 0.5), (-5.2, 5.0), (-6.0, 9.8), (-5.1, 13.3), (0.4, 14.4), (5.1, 13.2), (6.4, 9.8),
           (5.2, 5.0)],
    uarm_r=(2.6, 2.2), farm_r=(2.3, 1.9), thigh_r=(3.2, 2.5), shin_r=(2.6, 1.9), hand_r=1.9,
    fsh=(-1.4, 11.8), bsh=(2.2, 12.2), neck=(0.5, 13.6),
)
BODY_ARMOR = dict(
    torso=[(5.4, 0.5), (-5.4, 0.5), (-6.2, 5.0), (-7.0, 9.8), (-6.2, 13.6), (0.4, 14.8), (6.2, 13.5), (7.6, 9.8),
           (6.4, 5.0)],
    uarm_r=(3.0, 2.6), farm_r=(2.7, 2.4), thigh_r=(3.7, 3.0), shin_r=(3.1, 2.6), hand_r=2.1,
    fsh=(-1.6, 12.0), bsh=(2.4, 12.4), neck=(0.5, 13.9),
)
BODY_THIN = dict(
    torso=[(3.2, 0.5), (-3.3, 0.5), (-3.7, 5.0), (-4.3, 9.6), (-3.8, 12.9), (0.4, 13.9), (3.7, 12.8), (4.5, 9.4),
           (3.6, 5.0)],
    uarm_r=(1.7, 1.5), farm_r=(1.5, 1.3), thigh_r=(2.4, 1.9), shin_r=(1.9, 1.4), hand_r=1.4,
)
ARMOR_FOOT = [(2.0, -1.8), (2.0, 2.4), (-4.6, 2.4), (-4.6, 0.9), (-2.4, -0.4), (-0.4, -2.0)]


# ============================================================ 外观
def base_look(skin='skin', hair='hair_brown', eye='eye_brown', **kw):
    L = dict(skin=skin_mat(skin), hair=kw.pop('hair_mat', None) or mat(hair), eye=eye)
    L.update(kw)
    return L


def look_elwin():
    L = base_look('skin', 'hair_ash', 'eye_blue')
    navy = mat('cloth_navy')
    L.update(tunic=navy, sleeve=navy, pants=Mat('cloth_white', hi=0.55, sh=-0.12), boots=mat('leather'),
             glove=mat('leather'), boot_cuff=metal('gold'))
    L['head'] = head('elwin')
    cape = dark_of('cloth_navy', 1)
    L['torso_extra'] = [
        cape_fn(cape, length=9.5, collar=mat('cloth_white'), hem=metal('gold')),
        poly_local([(4.9, 5.2), (5.0, 9.5), (3.8, 12.2), (0.2, 12.6), (-2.3, 10.8), (-2.6, 7.0), (-0.8, 4.4)],
                   metal('steel'), Z_TORSO + 1, 'plate', sigma=1.2),
        skirt_fn(navy, length=6.0, lining=mat('cloth_white')),
        belt_fn(mat('leather'), buckle=metal('gold')),
    ]
    L['extra'] = [pauldron_fn(metal('steel'), 0.95)]
    L['weapon'] = dict(kind='sword', len=18, blade=metal('steel'), hilt=metal('gold'), gripm=mat('cloth_navy'))
    return L


def look_nora():
    L = base_look('skin', 'hair_brown', 'eye_green', body=BODY_F, scale=0.96)
    green = mat('cloth_green')
    L.update(tunic=green, sleeve=green, pants=mat('cloth_brown'), boots=dark_of('leather', 1), glove=mat('leather'),
             boot_top=0.55)
    L['head'] = head('nora')
    L['torso_extra'] = [
        cape_fn(mat('cloth_green'), length=9.0, width=0.9, folds=True),
        BP.quiver_fn(mat('leather'), fletch=CW[3]),
        poly_local([(4.5, 2.0), (4.7, 8.6), (3.2, 10.6), (0.2, 10.8), (-0.8, 6.0), (0.0, 2.0)], mat('leather'),
                   Z_TORSO + 1, 'vest', sigma=1.0),
        skirt_fn(green, length=4.5, flare=1.0),
        belt_fn(dark_of('leather', 1)),
        BP.hood_down_fn(green),
    ]
    L['extra'] = [BP.ponytail_fn(mat('hair_brown'), root=(4.0, -7.5), tie=mat('cloth_green'))]
    L['weapon'] = dict(kind='bow', half=11.5, curve=3.0, wood=mat('wood'))
    return L


def look_serin():
    L = base_look('skin', 'hair_black', 'eye_violet', body=BODY_F, scale=0.95)
    white = mat('cloth_white')
    sky = mat('cloth_sky')
    L.update(tunic=white, sleeve=white, pants=white, boots=mat('cloth_sky'), glove=skin_mat(), sleeve_flare=0.9,
             forearm=white)
    L['head'] = head('serin')
    L['extra'] = [BP.veil_fn(white, top=(2.0, -9.5), length=14.0)]
    L['torso_extra'] = [
        BP.robe_fn(white, hem=sky, flare=2.4),
        band_local(4.0, 13.0, -3.0, 13.2, 1.1, sky, Z_TORSO + 2, 'collar'),
        emblem_fn(DEER, {'y': GD[3]}, where=(2.2, 9.0)),
        belt_fn(sky, a0=4.2, a1=-4.4, b=3.0, r=0.9, z=Z_SKIRT + 1),
    ]
    L['weapon'] = dict(kind='staff', back=11, len=17, shaft=mat('cloth_white'), orn=metal('gold'),
                       gem=Mat('magic_blue', hi=0.2))
    return L


def look_doran():
    L = base_look('skin', 'hair_brown', 'eye_brown', body=BODY_ARMOR, scale=1.06, foot=ARMOR_FOOT)
    iron = metal('iron', spec=IR[4])
    olive = mat('cloth_olive')
    L.update(tunic=iron, sleeve=iron, forearm=iron, pants=iron, boots=iron, glove=iron, boot_top=0.0,
             knee_pad=iron, back_bias=-0.3)
    L['head'] = head('doran')
    L['torso_extra'] = [
        poly_local([(5.8, 0.5), (6.2, 9.6), (4.4, 13.0), (-2.0, 13.4), (-3.4, 9.0), (-2.6, 0.5)], olive,
                   Z_TORSO + 1, 'tabard', sigma=1.3),
        emblem_fn(SCRATCH, {'b': BK[1], 'x': PAL['cloth_olive'][4]}, where=(2.6, 8.2), group='tabard_em'),
        skirt_fn(olive, length=7.5, flare=1.2),
        belt_fn(mat('leather'), buckle=metal('iron')),
        BP.shield_fn(mat('wood'), 'tower', size=1.18, z=Z_TORSO + 8, arm='b', rim=metal('iron'),
                     emblem=shield_emblem([".ooo.", "ooooo", "ooOoo", "ooooo", ".ooo."],
                                          {'o': PAL['iron'][3], 'O': PAL['iron'][4]})),
    ]
    L['extra'] = [pauldron_fn(iron, 1.6)]
    L['weapon'] = dict(kind='lance', back=10, len=18, head_len=6)
    L['alt'] = dict(javelin=dict(kind='lance', back=5, len=12, head_len=5, head_w=1.6))
    return L


def look_sid():
    L = base_look('skin', 'hair_red', 'eye_amber', body=BODY_THIN, scale=0.97)
    jacket = mat('leather')
    L.update(tunic=jacket, sleeve=jacket, pants=dark_of('cloth_brown', 0), boots=dark_of('leather', 1),
             glove=dark_of('leather', 1), boot_top=0.55)
    L['head'] = head('sid')
    L['torso_extra'] = [
        poly_local([(4.6, 5.0), (4.4, 10.5), (2.6, 12.4), (1.0, 11.0), (1.8, 5.0)], mat('cloth_white'),
                   Z_TORSO + 1, 'shirt', level=3),
        belt_fn(dark_of('leather', 1), buckle=metal('steel')),
        skirt_fn(jacket, length=3.5, flare=0.8),
        BP.scarf_fn(mat('cloth_teal'), tail_len=10.0),
    ]
    L['weapon'] = dict(kind='dagger', len=10, grip=2.5, guard_w=1.8, hilt=metal('iron'))
    L['weapon2'] = dict(kind='dagger', len=9, grip=2.5, guard_w=1.8, hilt=metal('iron'))
    return L


def look_mira():
    L = base_look('skin', 'hair_lav', 'eye_gold', body=BODY_F, scale=0.92)
    teal = mat('cloth_teal')
    L.update(tunic=teal, sleeve=teal, forearm=teal, pants=teal, boots=dark_of('leather', 1), glove=skin_mat(),
             sleeve_flare=1.1)
    L['head'] = head('mira')
    L['torso_extra'] = [
        cape_fn(dark_of('cloth_teal', 1), length=11.0, width=0.85, hem=metal('gold')),
        BP.robe_fn(teal, hem=metal('gold'), flare=2.0),
        band_local(3.8, 12.8, -3.0, 13.2, 1.1, metal('gold'), Z_TORSO + 2, 'collar'),
        belt_fn(metal('gold'), a0=4.1, a1=-4.2, b=3.0, r=0.8, z=Z_SKIRT + 1),
    ]
    L['weapon'] = dict(kind='book', cover=mat('cloth_crimson'), gem=metal('gold'))
    return L


# ---------------- 敌方通用（黑鹰）
def look_soldier():
    L = base_look('skin', 'hair_brown', 'eye_brown')
    red = mat('cloth_crimson')
    L.update(tunic=red, sleeve=red, pants=mat('cloth_brown'), boots=mat('leather'), glove=mat('leather'))
    L['head'] = head('soldier')
    L['torso_extra'] = [
        poly_local([(5.0, 4.0), (5.2, 9.6), (3.8, 12.4), (-2.6, 12.6), (-4.2, 9.0), (-3.8, 4.0)], mat('leather'),
                   Z_TORSO + 1, 'cuirass', sigma=1.2),
        emblem_fn(EAGLE_S, {'b': BK[1]}, where=(2.2, 8.2), z=Z_TORSO + 2),
        skirt_fn(red, length=5.5),
        belt_fn(dark_of('leather', 1), buckle=metal('iron')),
    ]
    L['extra'] = [pauldron_fn(metal('iron'), 0.9)]
    L['weapon'] = dict(kind='lance', back=12, len=19, head_len=6)
    L['alt'] = dict(javelin=dict(kind='lance', back=5, len=12, head_len=5, head_w=1.6))
    return L


def look_fighter():
    L = base_look('skin_dk', 'hair_brown', 'eye_brown', body=BODY_BIG, scale=1.04)
    L.update(tunic=skin_mat('skin_dk'), sleeve=skin_mat('skin_dk'), pants=mat('cloth_brown'),
             boots=dark_of('leather', 1), glove=mat('leather'), bracer=mat('leather'), boot_top=0.5)
    L['head'] = head('fighter')
    L['torso_extra'] = [
        # 斜挎皮带 + 毛皮腰裙
        band_local(5.0, 11.0, -4.0, 2.5, 1.2, mat('leather'), Z_TORSO + 2, 'strap'),
        skirt_fn(mat('cloth_brown', hi=0.5), length=6.5, flare=1.4),
        belt_fn(mat('leather'), buckle=metal('iron')),
        # 胸肌/腹肌暗线
        lambda F, P, L_, info: F.add(m_line(info['T'](4.8, 8.2), info['T'](1.0, 7.4)), None, Z_TORSO + 0.5,
                                     'torso', inherit=-1),
    ]
    L['extra'] = [pauldron_fn(mat('leather'), 1.05)]
    L['weapon'] = dict(kind='axe', back=4, len=17, head_size=1.15)
    L['alt'] = dict(handaxe=dict(kind='handaxe'))
    return L


def look_mercenary():
    L = base_look('skin', 'hair_brown', 'eye_grey')
    L.update(tunic=mat('leather'), sleeve=mat('cloth_brown'), pants=mat('cloth_brown'), boots=dark_of('leather', 1),
             glove=dark_of('leather', 1), bracer=mat('leather'))
    L['head'] = head('mercenary')
    L['torso_extra'] = [
        cape_fn(mat('cloth_crimson'), length=8.0, width=0.95),
        poly_local([(5.0, 4.0), (5.2, 9.6), (3.8, 12.4), (-2.4, 12.6), (-3.8, 9.0), (-3.4, 4.0)], metal('iron'),
                   Z_TORSO + 1, 'plate', sigma=1.2),
        skirt_fn(mat('leather'), length=6.0),
        belt_fn(dark_of('leather', 1), buckle=metal('iron')),
    ]
    L['extra'] = [pauldron_fn(metal('iron'), 1.0)]
    L['weapon'] = dict(kind='sword', len=21, bw=2, hilt=metal('iron'), gripm=mat('leather'), guard_w=3.0)
    return L


def look_archer():
    L = base_look('skin', 'hair_black', 'eye_brown')
    red = mat('cloth_crimson')
    L.update(tunic=red, sleeve=red, pants=mat('cloth_brown'), boots=mat('leather'), glove=mat('leather'))
    L['head'] = head('archer')
    L['torso_extra'] = [
        BP.quiver_fn(mat('leather'), fletch=CW[3]),
        poly_local([(4.8, 3.0), (5.0, 9.4), (3.4, 12.2), (-2.4, 12.4), (-3.6, 8.5), (-3.2, 3.0)], mat('leather'),
                   Z_TORSO + 1, 'vest', sigma=1.1),
        skirt_fn(red, length=5.0),
        belt_fn(dark_of('leather', 1)),
    ]
    L['weapon'] = dict(kind='bow', half=11.5, curve=3.0, wood=dark_of('wood', 0))
    return L


def look_mage_e():
    L = base_look('skin', 'hair_black', 'eye_brown')
    red = mat('cloth_crimson')
    L.update(tunic=red, sleeve=red, forearm=red, pants=red, boots=dark_of('leather', 1), glove=skin_mat(),
             sleeve_flare=1.0)
    L['head'] = head('mage_e')
    L['torso_extra'] = [
        cape_fn(dark_of('cloth_crimson', 1), length=11.0, width=0.85),
        BP.robe_fn(red, hem=metal('gold'), flare=2.0),
        band_local(3.8, 12.8, -3.0, 13.2, 1.1, mat('cloth_black'), Z_TORSO + 2, 'collar'),
        belt_fn(mat('cloth_black'), a0=4.1, a1=-4.2, b=3.0, r=0.9, z=Z_SKIRT + 1),
    ]
    L['weapon'] = dict(kind='book', cover=mat('cloth_black'), gem=metal('gold'))
    return L


def look_darkmage(boss=False):
    L = base_look('skin_old', 'hair_black', 'eye_red', body=BODY_THIN, scale=1.07 if boss else 1.0)
    blk = mat('cloth_black', hi=0.3)
    L.update(tunic=blk, sleeve=blk, forearm=blk, pants=blk, boots=mat('cloth_black'), glove=skin_mat('skin_old'),
             sleeve_flare=1.3)
    L['head'] = head('morgan' if boss else 'darkmage')
    L['torso_extra'] = [
        cape_fn(mat('cloth_crimson') if boss else dark_of('cloth_crimson', 1), length=12.0, width=1.0,
                hem=metal('gold') if boss else None),
        BP.robe_fn(blk, hem=mat('cloth_crimson'), flare=2.6),
        band_local(4.0, 12.6, -3.2, 13.4, 1.4, mat('cloth_crimson'), Z_TORSO + 2, 'collar'),
        belt_fn(mat('cloth_crimson'), a0=4.1, a1=-4.2, b=3.0, r=0.9, z=Z_SKIRT + 1),
    ]
    if boss:
        L['torso_extra'].append(poly_local([(3.8, 13.0), (4.8, 12.4), (5.4, -9.0), (2.6, -9.0), (2.2, 12.4)],
                                           mat('cloth_crimson'), Z_SKIRT + 2, 'stole', sigma=0.9))
        L['torso_extra'].append(band_local(5.2, -8.6, 2.8, -8.6, 0.7, metal('gold'), Z_SKIRT + 2.5, 'stole_t'))
        L['torso_extra'].append(emblem_fn(EAGLE_S, {'b': BK[1]}, where=(3.8, 4.0), z=Z_SKIRT + 3))
    L['weapon'] = dict(kind='book', cover=mat('magic_dark'), gem=Mat('eye_red', hi=0.2))
    return L


def look_knight_e():
    L = base_look('skin', 'hair_black', 'eye_brown', body=BODY_ARMOR, scale=1.06, foot=ARMOR_FOOT)
    iron = metal('iron', spec=IR[4])
    red = mat('cloth_crimson')
    L.update(tunic=iron, sleeve=iron, forearm=iron, pants=iron, boots=iron, glove=iron, boot_top=0.0, knee_pad=iron,
             back_bias=-0.3)
    L['head'] = head('knight_e')
    L['torso_extra'] = [
        poly_local([(5.8, 0.5), (6.2, 9.6), (4.4, 13.0), (-2.0, 13.4), (-3.4, 9.0), (-2.6, 0.5)], red,
                   Z_TORSO + 1, 'tabard', sigma=1.3),
        emblem_fn(EAGLE_S, {'b': BK[1]}, where=(2.6, 8.2), group='tabard_em'),
        skirt_fn(red, length=7.5, flare=1.2),
        belt_fn(mat('leather'), buckle=metal('iron')),
        BP.shield_fn(red, 'tower', size=1.18, z=Z_TORSO + 8, arm='b', rim=iron,
                     emblem=shield_emblem(EAGLE_L, {'b': BK[1]})),
    ]
    L['extra'] = [pauldron_fn(iron, 1.6)]
    L['weapon'] = dict(kind='lance', back=10, len=18, head_len=6)
    L['alt'] = dict(javelin=dict(kind='lance', back=5, len=12, head_len=5, head_w=1.6))
    return L


def look_priest():
    L = base_look('skin', 'hair_black', 'eye_brown', body=BODY_THIN)
    red = mat('cloth_crimson')
    L.update(tunic=red, sleeve=red, forearm=red, pants=red, boots=dark_of('leather', 1), glove=skin_mat(),
             sleeve_flare=1.0)
    L['head'] = head('priest')
    L['torso_extra'] = [
        BP.robe_fn(red, hem=metal('gold'), flare=2.2),
        # 白色圣带
        poly_local([(3.6, 13.0), (4.4, 12.4), (4.8, -8.0), (3.0, -8.0), (2.4, 12.4)], mat('cloth_white'),
                   Z_SKIRT + 2, 'stole', sigma=0.9),
        emblem_fn(["y.y", ".y.", "yyy", ".y."], {'y': GD[3]}, where=(3.7, 4.0), z=Z_SKIRT + 3),
        belt_fn(mat('cloth_black'), a0=4.1, a1=-4.2, b=3.0, r=0.9, z=Z_SKIRT + 1),
    ]
    L['weapon'] = dict(kind='staff', back=11, len=17, shaft=mat('wood'), orn=metal('gold'),
                       gem=Mat('eye_red', hi=0.2))
    return L


def look_general(boss=None):
    L = base_look('skin_old' if boss == 'hagen' else 'skin', 'hair_grey', 'eye_grey', body=BODY_ARMOR, scale=1.12,
                  foot=ARMOR_FOOT)
    iron = metal('iron', spec=IR[4])
    red = mat('cloth_crimson')
    L.update(tunic=iron, sleeve=iron, forearm=iron, pants=iron, boots=iron, glove=iron, boot_top=0.0,
             knee_pad=metal('gold') if boss is None else iron, back_bias=-0.3)
    L['head'] = head('hagen' if boss == 'hagen' else 'general')
    L['torso_extra'] = [
        cape_fn(red, length=13.0, width=1.15, hem=metal('gold')),
        poly_local([(6.2, 4.0), (6.6, 9.8), (4.6, 13.2), (-2.2, 13.6), (-3.6, 9.0), (-2.8, 4.0)], iron,
                   Z_TORSO + 1, 'plate', sigma=1.4),
        band_local(6.4, 9.6, 4.6, 13.0, 0.7, metal('gold'), Z_TORSO + 1.5, 'plate', inherit=0),
        emblem_fn(EAGLE_S, {'b': CR[2]}, where=(2.6, 8.8), z=Z_TORSO + 2),
        skirt_fn(iron, length=8.0, flare=1.8),
        skirt_fn(red, length=9.0, flare=1.0, z=Z_SKIRT - 0.5, group='skirt2'),
        belt_fn(mat('leather'), buckle=metal('gold')),
        BP.shield_fn(red, 'tower', size=1.2, z=Z_TORSO + 8, arm='b',
                     rim=metal('gold'), emblem=shield_emblem(EAGLE_L, {'b': BK[1] if boss != 'hagen' else CR[3]})),
    ]
    L['extra'] = [pauldron_fn(iron, 1.75)]
    if boss == 'hagen':
        L['weapon'] = dict(kind='lance', back=10, len=18, head_len=6)
        L['alt'] = dict(javelin=dict(kind='lance', back=5, len=12, head_len=5, head_w=1.6))
    else:
        L['weapon'] = dict(kind='axe', back=5, len=17, head_size=1.25)
        L['alt'] = dict(handaxe=dict(kind='handaxe'))
    return L


def look_gord():
    L = base_look('skin', 'hair_brown', 'eye_brown', body=BODY_BIG, scale=1.1)
    lea = mat('leather')
    L.update(tunic=lea, sleeve=skin_mat(), forearm=skin_mat(), pants=mat('cloth_black'), boots=dark_of('leather', 1),
             glove=mat('leather'), bracer=dark_of('leather', 1), boot_top=0.5)
    L['head'] = head('gord')
    L['torso_extra'] = [
        cape_fn(mat('cloth_crimson'), length=7.0, width=1.0),
        poly_local([(5.8, 3.0), (6.4, 9.8), (4.6, 13.0), (-2.2, 13.4), (-3.6, 9.0), (-3.0, 3.0)], mat('cloth_black'),
                   Z_TORSO + 1, 'jerkin', sigma=1.2),
        emblem_fn(EAGLE_S, {'b': CR[3]}, where=(2.6, 8.4), z=Z_TORSO + 2),
        skirt_fn(lea, length=6.5, flare=1.6),
        belt_fn(dark_of('leather', 1), buckle=metal('iron')),
    ]
    L['extra'] = [pauldron_fn(metal('iron'), 1.25)]
    L['weapon'] = dict(kind='axe', back=4, len=18, head_size=1.3)
    L['alt'] = dict(handaxe=dict(kind='handaxe'))
    return L


def look_valder():
    L = base_look('skin', 'hair_black', 'eye_grey', body=BODY_BIG, scale=1.1, hair_mat=HAIR_VALDER)
    blk = metal('cloth_black', spec=BK[4], hi=0.3, sh=-0.25)
    L.update(tunic=blk, sleeve=blk, forearm=blk, pants=blk, boots=blk, glove=blk, boot_top=0.0,
             knee_pad=metal('gold'), back_bias=-0.25, foot=ARMOR_FOOT)
    L['head'] = head('valder')
    L['torso_extra'] = [
        cape_fn(mat('cloth_crimson'), length=15.0, width=1.35, hem=metal('gold'), collar=mat('cloth_crimson')),
        poly_local([(5.2, 4.0), (5.8, 9.8), (4.2, 13.0), (-2.2, 13.4), (-3.6, 9.0), (-2.8, 4.0)], blk,
                   Z_TORSO + 1, 'plate', sigma=1.3),
        band_local(5.6, 9.6, 4.2, 12.8, 0.7, metal('gold'), Z_TORSO + 1.5, 'plate', inherit=0),
        emblem_fn(EAGLE_S, {'b': CR[3]}, where=(2.4, 8.6), z=Z_TORSO + 2),
        skirt_fn(blk, length=8.0, flare=1.6),
        skirt_fn(mat('cloth_crimson'), length=9.5, flare=0.8, z=Z_SKIRT - 0.5, group='skirt2'),
        belt_fn(mat('leather'), buckle=metal('gold')),
    ]
    L['extra'] = [pauldron_fn(blk, 1.45)]
    L['weapon'] = dict(kind='greatsword', len=26, bw=4, hilt=metal('gold'), gripm=mat('cloth_crimson'), guard_w=4.2,
                       grip=4, smear='red')
    L['alt'] = dict(javelin=dict(kind='lance', back=5, len=12, head_len=5, head_w=1.6))
    return L


def look_martha():
    L = base_look('skin_old', 'hair_grey', 'eye_brown', body=BODY_F, scale=0.88)
    dress = mat('cloth_olive')
    L.update(tunic=dress, sleeve=dress, forearm=dress, pants=dress, boots=dark_of('leather', 1),
             glove=skin_mat('skin_old'))
    L['head'] = head('martha')
    L['torso_extra'] = [
        BP.robe_fn(dress, flare=1.6),
        poly_local([(4.2, 6.0), (4.6, -8.5), (-1.0, -8.5), (-0.6, 6.0)], mat('cloth_white', hi=0.5, sh=-0.1),
                   Z_SKIRT + 2, 'apron', sigma=0.9),
        cape_fn(mat('cloth_brown'), length=0.0, width=0.7, folds=False),
    ]
    L['weapon'] = dict(kind='stick', back=5, len=11, shaft=mat('wood'))
    return L


# ============================================================ 动作原型
def scale_pose(p, s):
    q = dict(p)
    for k in ('hip', 'ff', 'bf', 'fh', 'bh', 'head'):
        if k in q and q[k] is not None:
            v = q[k]
            q[k] = tuple([v[0] * s, v[1] * s] + list(v[2:]))
    if 'thrust' in q:
        q['thrust'] = q['thrust'] * s
    return q


def finish(A, s):
    return {k: [(scale_pose(p, s), d) for (p, d) in seq] for k, seq in A.items()}


def anims_sword(s=1.0, heavy=False, ranged=False):
    idle = dict(hip=(0, -22.0), lean=6, ff=(-7.5, -2.4), bf=(6.5, -2.4), fh=(-6.5, 9.0), wa=116, bh=(3.0, 10.5), cape=0)
    idle1 = P(idle, hip=(0, -21.0), lean=7, fh=(-6.5, 9.5), wa=114, bh=(3.0, 11.0), cape=0.6)
    a0 = dict(hip=(1.5, -22.5), lean=-2, ff=(-6.5, -2.4), bf=(7.5, -2.4), fh=(4.5, -11.5), wa=-168, bh=(-3, 8),
              cape=1)
    a1 = dict(hip=(3, -21.5), lean=-8, ff=(-6, -2.4), bf=(8, -2.4), fh=(5.5, -3.5), wa=-112, wz=Z_TORSO - 1,
              bh=(-5, 6), cape=2, head=(0.5, 0), arm_behind_head=True)
    a2 = dict(hip=(-7, -19.5), lean=24, ff=(-16, -2.4), bf=(5, -2.4), fh=(-9, 5), wa=62, smear=(-112, -298),
              bh=(5, 7), cape=5)
    a3 = dict(hip=(-7, -19), lean=26, ff=(-16, -2.4), bf=(5, -2.4), fh=(-7, 8.5), wa=38, bh=(5.5, 6), cape=6.5)
    a4 = dict(hip=(-2, -21), lean=12, ff=(-11, -2.4), bf=(6, -2.4), fh=(-6.5, 8.5), wa=100, bh=(3, 9), cape=3)
    c0 = dict(hip=(1, -22.5), lean=-4, ff=(-7, -2.4), bf=(7, -2.4), fh=(3.5, -11.5), wa=176, bh=(-2, 9), glint=True,
              cape=1)
    c1 = dict(hip=(-2, -33), lean=6, ff=(-6, -15, 40), bf=(5, -13, 30), fh=(4, -7), wa=-120, bh=(-4, 4), cape=4,
              cape_lift=3, arm_behind_head=True, wz=Z_TORSO - 1)
    c2 = dict(hip=(-9, -18), lean=30, ff=(-18, -2.4), bf=(6, -2.4), fh=(-9, 6), wa=50, smear=(-120, -310, 1.8),
              bh=(6, 6), cape=7)
    c3 = dict(hip=(-9, -16.5), lean=33, ff=(-18, -2.4), bf=(6, -2.4), fh=(-7.5, 8), wa=40, bh=(6, 5), cape=7.5)
    c4 = P(a4)
    d0 = dict(hip=(6, -23), lean=-8, ff=(-1, -3.5, 15), bf=(10, -2.4), fh=(-3.5, 8), wa=122, bh=(3, 9), cape=-2)
    d1 = dict(hip=(10, -22), lean=-14, ff=(2, -2.4), bf=(13, -2.4), fh=(-2.5, 7.5), wa=132, bh=(4, 8), cape=-3,
              head=(0.5, 0))
    h0 = dict(hip=(4, -21.5), lean=-14, ff=(-5, -2.4), bf=(9, -2.4), fh=(4, 6), wa=-150, bh=(6, 4), head=(1, 1),
              hv='hurt', cape=-2, arm_behind_head=True)
    if heavy:
        # 大剑：双手握，动作更沉
        for p in (idle, idle1, a0, a1, a2, a3, a4, c0, c1, c2, c3, c4, d0, d1):
            p['two_hand'] = 3.5
        idle.update(fh=(-6, 8), wa=128)
        idle1.update(fh=(-6, 8.5), wa=126)
        a2.update(hip=(-5, -19.5), ff=(-14, -2.4))
        c2.update(hip=(-7, -18), ff=(-16, -2.4))
        c3.update(hip=(-7, -16.5), ff=(-16, -2.4))
        c0.update(fh=(3.0, -6.0), wa=170)
        a0.update(fh=(4.5, -6.0), wa=-155)
    A = {
        'idle': [(idle, 30), (idle1, 30)],
        'attack': [(a0, 10 if heavy else 8), (a1, 12 if heavy else 10), (a2, 4 if heavy else 3), (a3, 20), (a4, 9)],
        'crit': [(c0, 26), (c1, 8), (c2, 4), (c3, 24), (c4, 9)],
        'dodge': [(d0, 6), (d1, 16)],
        'hurt': [(h0, 12)],
    }
    E = {'attack': {'hit': 2}, 'crit': {'hit': 2}}
    if ranged:
        r0 = dict(hip=(2, -22), lean=-6, ff=(-6, -2.4), bf=(7, -2.4), fh=(5, -6), wa=110, bh=(-5, 5), wpn='javelin',
                  arm_behind_head=True, cape=1)
        r1 = dict(hip=(-5, -21), lean=16, ff=(-13, -2.4), bf=(6, -2.4), fh=(-10, -1), wa=None, bh=(4, 6), cape=4)
        r2 = dict(hip=(-5, -20.5), lean=18, ff=(-13, -2.4), bf=(6, -2.4), fh=(-7, 7), wa=None, bh=(4, 8), cape=4)
        r3 = dict(hip=(-2, -21.5), lean=8, ff=(-10, -2.4), bf=(6, -2.4), fh=(-5, 9), wa=None, bh=(3, 10), cape=2)
        A['ranged'] = [(r0, 16), (r1, 4), (r2, 14), (r3, 8)]
        E['ranged'] = {'shoot': 1}
    return finish(A, s), E


def anims_dagger(s=1.0):
    """盗贼：双短剑，快速两连斩。"""
    idle = dict(hip=(0, -20.5), lean=14, ff=(-8, -2.4), bf=(7, -2.4), fh=(-6, 7), wa=100, bh=(-3, 9), wa2=-10,
                cape=0.5)
    idle1 = P(idle, hip=(0, -19.8), lean=15, fh=(-6, 7.5), bh=(-3, 9.5), cape=1.0)
    a0 = dict(hip=(2, -18.5), lean=22, ff=(-7, -2.4), bf=(9, -2.4), fh=(2, 3), wa=-130, bh=(-5, 7), wa2=60, cape=2,
              arm_behind_head=False)
    a1 = dict(hip=(-8, -19.5), lean=24, ff=(-17, -2.4), bf=(5, -2.4), fh=(-10, 3), wa=80, smear=(-130, -280),
              bh=(-2, 8), wa2=80, cape=5)
    a2 = dict(hip=(-9, -19), lean=20, ff=(-17, -2.4), bf=(5, -2.4), fh=(-3, 9), wa=40, bh=(-11, 1), wa2=110,
              smear2=(20, 110), cape=6, back_arm_front=True, wz2=Z_FARM + 2)
    a3 = dict(hip=(-8, -19), lean=18, ff=(-16, -2.4), bf=(5, -2.4), fh=(-5, 8), wa=70, bh=(-9, 3), wa2=100, cape=5,
              back_arm_front=True, wz2=Z_FARM + 2)
    a4 = P(idle, hip=(-3, -20.5), cape=3)
    c0 = dict(hip=(1, -16), lean=30, ff=(-7, -2.4), bf=(9, -2.4), fh=(-2, 10), wa=150, bh=(-6, 9), wa2=130,
              glint='small', glint2=True, cape=2)
    c1 = dict(hip=(-4, -36), lean=-10, ff=(-7, -18, 30), bf=(3, -17, 30), fh=(4, -8), wa=-140, bh=(-1, -8), wa2=150,
              cape=5, cape_lift=4, arm_behind_head=True)
    c2 = dict(hip=(-10, -18), lean=28, ff=(-19, -2.4), bf=(6, -2.4), fh=(-11, 5), wa=55, smear=(-140, -305, 1.6),
              bh=(-8, 8), wa2=20, smear2=(150, 20), cape=7, back_arm_front=True, wz2=Z_FARM + 2)
    c3 = dict(hip=(-10, -16.5), lean=30, ff=(-19, -2.4), bf=(6, -2.4), fh=(-7, 9), wa=40, bh=(-6, 9), wa2=30, cape=7)
    c4 = P(a4)
    d0 = dict(hip=(7, -22), lean=-5, ff=(0, -4.0, 20), bf=(11, -2.4), fh=(-4, 7), wa=110, bh=(-1, 8), wa2=80, cape=-2)
    d1 = dict(hip=(12, -24), lean=-12, ff=(5, -6, 30), bf=(14, -3.0, 10), fh=(-3, 6), wa=120, bh=(0, 7), wa2=90,
              cape=-3)
    h0 = dict(hip=(4, -20.5), lean=-10, ff=(-6, -2.4), bf=(9, -2.4), fh=(3, 7), wa=-150, bh=(2, 6), wa2=140,
              head=(1, 1), hv='hurt', cape=-2)
    A = {
        'idle': [(idle, 26), (idle1, 26)],
        'attack': [(a0, 8), (a1, 3), (a2, 3), (a3, 14), (a4, 8)],
        'crit': [(c0, 20), (c1, 8), (c2, 4), (c3, 22), (c4, 8)],
        'dodge': [(d0, 5), (d1, 14)],
        'hurt': [(h0, 12)],
    }
    return finish(A, s), {'attack': {'hit': 2}, 'crit': {'hit': 2}}


def anims_lance(s=1.0):
    """士兵：双手持枪突刺 + 投枪。"""
    idle = dict(hip=(0, -22), lean=5, ff=(-7, -2.4), bf=(6.5, -2.4), fh=(-6, 8), wa=100, two_hand=7, cape=0)
    idle1 = P(idle, hip=(0, -21), lean=6, fh=(-6, 8.5))
    a0 = dict(hip=(2.5, -21.5), lean=-3, ff=(-6, -2.4), bf=(8, -2.4), fh=(-1, 7), wa=98, two_hand=7, cape=1)
    a1 = dict(hip=(-6, -20), lean=20, ff=(-15, -2.4), bf=(5, -2.4), fh=(-10, 4), wa=95, two_hand=6, thrust=12, cape=4)
    a2 = dict(hip=(-6, -20), lean=20, ff=(-15, -2.4), bf=(5, -2.4), fh=(-9.5, 4.5), wa=96, two_hand=6, cape=4.5)
    a3 = dict(hip=(-2, -21.5), lean=8, ff=(-11, -2.4), bf=(6, -2.4), fh=(-6, 8), wa=100, two_hand=7, cape=2)
    c0 = dict(hip=(1, -22.5), lean=-4, ff=(-7, -2.4), bf=(7, -2.4), fh=(-3, -6), wa=150, two_hand=6, glint=True,
              cape=1, arm_behind_head=True)
    c1 = dict(hip=(4, -17), lean=10, ff=(-6, -2.4), bf=(10, -2.4), fh=(1, 8), wa=92, two_hand=7, cape=2)
    c2 = dict(hip=(-5, -17.5), lean=28, ff=(-14, -2.4), bf=(7, -2.4), fh=(-10, 3), wa=93, two_hand=6, thrust=16,
              cape=7)
    c3 = dict(hip=(-5, -17.5), lean=28, ff=(-14, -2.4), bf=(7, -2.4), fh=(-9.5, 3.5), wa=94, two_hand=6, cape=7)
    c4 = P(a3)
    r0 = dict(hip=(2, -22), lean=-6, ff=(-6, -2.4), bf=(7, -2.4), fh=(5, -6), wa=110, bh=(-5, 5), wpn='javelin',
              arm_behind_head=True, cape=1)
    r1 = dict(hip=(-5, -21), lean=16, ff=(-13, -2.4), bf=(6, -2.4), fh=(-10, -1), wa=None, bh=(4, 6), cape=4)
    r2 = dict(hip=(-5, -20.5), lean=18, ff=(-13, -2.4), bf=(6, -2.4), fh=(-7, 7), wa=None, bh=(4, 8), cape=4)
    r3 = dict(hip=(-2, -21.5), lean=8, ff=(-10, -2.4), bf=(6, -2.4), fh=(-5, 9), wa=None, bh=(3, 10), cape=2)
    d0 = dict(hip=(6, -23), lean=-8, ff=(-1, -3.5, 15), bf=(10, -2.4), fh=(-4, 8), wa=105, two_hand=7, cape=-2)
    d1 = dict(hip=(10, -22), lean=-14, ff=(2, -2.4), bf=(13, -2.4), fh=(-3, 7.5), wa=110, two_hand=7, cape=-3)
    h0 = dict(hip=(4, -21.5), lean=-14, ff=(-5, -2.4), bf=(9, -2.4), fh=(0, 8), wa=120, two_hand=7, head=(1, 1),
              hv='hurt', cape=-2)
    A = {
        'idle': [(idle, 30), (idle1, 30)],
        'attack': [(a0, 12), (a1, 4), (a2, 16), (a3, 10)],
        'crit': [(c0, 24), (c1, 10), (c2, 4), (c3, 20), (c4, 10)],
        'ranged': [(r0, 16), (r1, 4), (r2, 14), (r3, 8)],
        'dodge': [(d0, 6), (d1, 16)],
        'hurt': [(h0, 12)],
    }
    return finish(A, s), {'attack': {'hit': 1}, 'crit': {'hit': 2}, 'ranged': {'shoot': 1}}


def anims_armor(s=1.0, weapon='lance'):
    """重甲：后臂持大盾护身，前手持枪（突刺）或斧（下劈）。"""
    base = dict(hip=(0, -20.5), lean=4, ff=(-7, -2.4), bf=(6, -2.4), bh=(-6, 6), cape=0)
    if weapon == 'lance':
        idle = P(base, fh=(-3, 8), wa=100)
        idle1 = P(idle, hip=(0, -19.8), fh=(-3, 8.5))
        a0 = P(base, hip=(2, -20.5), lean=-2, fh=(1, 6), wa=98, bh=(-6, 5), cape=1)
        a1 = P(base, hip=(-5, -19.5), lean=14, ff=(-12, -2.4), fh=(-9, 4), wa=94, bh=(-5, 5), thrust=12, cape=3)
        a2 = P(base, hip=(-5, -19.5), lean=14, ff=(-12, -2.4), fh=(-8.5, 4.5), wa=95, bh=(-5, 5), cape=3)
        a3 = P(idle, hip=(-1, -20.5))
        c0 = P(base, hip=(1, -21), lean=-3, fh=(-1, -7), wa=140, glint=True, arm_behind_head=True, cape=1)
        c1 = P(base, hip=(3, -18), lean=8, ff=(-6, -2.4), bf=(9, -2.4), fh=(1, 7), wa=93, cape=2)
        c2 = P(base, hip=(-5, -18.5), lean=22, ff=(-13, -2.4), bf=(6, -2.4), fh=(-9.5, 3), wa=93, thrust=16, cape=5)
        c3 = P(c2, thrust=None, fh=(-9.5, 3.5))
        c3.pop('thrust')
        ev = {'attack': {'hit': 1}, 'crit': {'hit': 2}}
        rw = 'javelin'
    else:
        idle = P(base, fh=(-5.5, 7), wa=128)
        idle1 = P(idle, hip=(0, -19.8), fh=(-5.5, 7.5), wa=126)
        a0 = P(base, hip=(2, -21), lean=-4, fh=(2, -8), wa=-150, arm_behind_head=True, cape=1)
        a1 = P(base, hip=(3, -20.5), lean=-8, fh=(4, -5), wa=-115, wz=Z_TORSO - 1, arm_behind_head=True, cape=2)
        a2 = P(base, hip=(-6, -18.5), lean=24, ff=(-13, -2.4), fh=(-9, 6), wa=55, smear=(-115, -305, 1.6), cape=4)
        a3 = P(base, hip=(-6, -18.5), lean=26, ff=(-13, -2.4), fh=(-7, 8), wa=42, cape=4)
        c0 = P(base, hip=(1, -21), lean=-4, fh=(0, -10), wa=175, glint=True, arm_behind_head=True, cape=1)
        c1 = P(base, hip=(2, -20), lean=-10, fh=(4, -6), wa=-120, wz=Z_TORSO - 1, arm_behind_head=True, cape=2)
        c2 = P(base, hip=(-7, -17.5), lean=30, ff=(-14, -2.4), fh=(-9, 6), wa=50, smear=(-120, -310, 2.0), cape=6)
        c3 = P(base, hip=(-8, -17), lean=32, ff=(-15, -2.4), fh=(-7, 8), wa=40, cape=6)
        ev = {'attack': {'hit': 2}, 'crit': {'hit': 2}}
        rw = 'handaxe'
    a4 = P(idle, hip=(-1, -20.5))
    c4 = P(idle, hip=(-1, -20.5))
    r0 = P(base, hip=(2, -20.5), lean=-6, fh=(5, -6), wa=115 if rw == 'javelin' else -140, wpn=rw,
           arm_behind_head=True, cape=1)
    r1 = P(base, hip=(-4, -20), lean=14, ff=(-10, -2.4), fh=(-10, -1), wa=None, cape=3)
    r2 = P(base, hip=(-4, -19.5), lean=16, ff=(-10, -2.4), fh=(-6, 7), wa=None, cape=3)
    r3 = P(base, hip=(-1, -20.5), fh=(-3, 9), wa=None)
    d0 = P(idle, hip=(4, -20.5), lean=-6, ff=(-3, -2.4), bf=(9, -2.4), bh=(-7, 2), cape=-1)
    d1 = P(idle, hip=(6, -20), lean=-9, ff=(-1, -2.4), bf=(10, -2.4), bh=(-7, 1), cape=-2)
    h0 = P(idle, hip=(3, -20.5), lean=-12, ff=(-5, -2.4), bf=(8, -2.4), head=(1, 1), hv='hurt', bh=(-3, 7), cape=-1)
    if weapon == 'lance':
        attack = [(a0, 14), (a1, 4), (a2, 16), (a3, 10)]
        crit = [(c0, 24), (c1, 10), (c2, 4), (c3, 20), (c4, 10)]
    else:
        attack = [(a0, 10), (a1, 12), (a2, 4), (a3, 18), (a4, 10)]
        crit = [(c0, 24), (c1, 10), (c2, 4), (c3, 22), (c4, 10)]
    A = {
        'idle': [(idle, 32), (idle1, 32)],
        'attack': attack,
        'crit': crit,
        'ranged': [(r0, 18), (r1, 4), (r2, 14), (r3, 10)],
        'dodge': [(d0, 8), (d1, 14)],
        'hurt': [(h0, 12)],
    }
    ev['ranged'] = {'shoot': 1}
    return finish(A, s), ev


def anims_axe(s=1.0):
    """战士：斧扛肩，双手抡劈 + 投掷手斧。"""
    idle = dict(hip=(0, -21.5), lean=10, ff=(-7.5, -2.4), bf=(7, -2.4), fh=(-6.5, 7), wa=126, bh=(2, 10), cape=0)
    idle1 = P(idle, hip=(0, -20.5), lean=11, fh=(-6.5, 7.5), wa=124)
    a0 = dict(hip=(2, -22), lean=-4, ff=(-7, -2.4), bf=(8, -2.4), fh=(1, -8), wa=-150, two_hand=4,
              arm_behind_head=True, cape=1)
    a1 = dict(hip=(3.5, -21), lean=-10, ff=(-6, -2.4), bf=(8.5, -2.4), fh=(4, -5), wa=-115, two_hand=4,
              wz=Z_TORSO - 1, arm_behind_head=True, cape=2)
    a2 = dict(hip=(-7, -18.5), lean=28, ff=(-15, -2.4), bf=(6, -2.4), fh=(-9, 6), wa=55, two_hand=4,
              smear=(-115, -305, 1.6), cape=5)
    a3 = dict(hip=(-7, -18), lean=30, ff=(-15, -2.4), bf=(6, -2.4), fh=(-7, 8), wa=42, two_hand=4, cape=5)
    a4 = P(idle, hip=(-2, -21))
    c0 = dict(hip=(1, -22), lean=-6, ff=(-8, -2.4), bf=(8, -2.4), fh=(0, -10), wa=175, bh=(-3, 3), glint=True,
              arm_behind_head=True, cape=1)
    c1 = dict(hip=(-3, -30), lean=0, ff=(-7, -13, 35), bf=(5, -11, 30), fh=(4, -6), wa=-120, two_hand=4,
              arm_behind_head=True, wz=Z_TORSO - 1, cape=4, cape_lift=3)
    c2 = dict(hip=(-9, -17), lean=32, ff=(-17, -2.4), bf=(6, -2.4), fh=(-9, 7), wa=45, two_hand=4,
              smear=(-120, -315, 2.0), cape=7)
    c3 = dict(hip=(-9, -16), lean=34, ff=(-17, -2.4), bf=(6, -2.4), fh=(-7, 8), wa=40, two_hand=4, cape=7)
    c4 = P(a4)
    r0 = dict(hip=(2, -21.5), lean=-6, ff=(-6, -2.4), bf=(7, -2.4), fh=(5, -5), wa=-140, bh=(-5, 5), wpn='handaxe',
              arm_behind_head=True, cape=1)
    r1 = dict(hip=(-5, -20.5), lean=18, ff=(-13, -2.4), bf=(6, -2.4), fh=(-10, 0), wa=None, bh=(4, 6), cape=4)
    r2 = dict(hip=(-5, -20), lean=20, ff=(-13, -2.4), bf=(6, -2.4), fh=(-7, 8), wa=None, bh=(4, 8), cape=4)
    r3 = dict(hip=(-2, -21), lean=10, ff=(-10, -2.4), bf=(6.5, -2.4), fh=(-4, 9), wa=None, bh=(2, 10), cape=2)
    d0 = dict(hip=(6, -22.5), lean=-6, ff=(-1, -3.5, 15), bf=(10, -2.4), fh=(-5, 7), wa=135, bh=(3, 9), cape=-2)
    d1 = dict(hip=(10, -21.5), lean=-12, ff=(2, -2.4), bf=(13, -2.4), fh=(-4, 6.5), wa=142, bh=(4, 8), cape=-3)
    h0 = dict(hip=(4, -21), lean=-12, ff=(-5, -2.4), bf=(9, -2.4), fh=(-2, 7), wa=150, bh=(5, 5), head=(1, 1),
              hv='hurt', cape=-2)
    A = {
        'idle': [(idle, 30), (idle1, 30)],
        'attack': [(a0, 10), (a1, 12), (a2, 4), (a3, 18), (a4, 10)],
        'crit': [(c0, 26), (c1, 8), (c2, 4), (c3, 24), (c4, 10)],
        'ranged': [(r0, 16), (r1, 4), (r2, 14), (r3, 8)],
        'dodge': [(d0, 6), (d1, 16)],
        'hurt': [(h0, 12)],
    }
    return finish(A, s), {'attack': {'hit': 2}, 'crit': {'hit': 2}, 'ranged': {'shoot': 1}}


def anims_bow(s=1.0):
    """弓：前(近侧)手持弓，后(远侧)手拉弦到脸颊。"""
    idle = dict(hip=(0, -22), lean=4, ff=(-6.5, -2.4), bf=(6.5, -2.4), fh=(-4.5, 10), wa=96, bh=(2, 10), cape=0)
    idle1 = P(idle, hip=(0, -21), lean=5, fh=(-4.5, 10.5), bh=(2, 10.5))
    a0 = dict(fsh_fwd=3.5, hip=(0.5, -22), lean=2, ff=(-7, -2.4), bf=(6.5, -2.4), fh=(-11, 1.5), wa=92, bh=(-7, 0), be=1,
              drawn=True, arrow=True, cape=0.5)
    a1 = dict(fsh_fwd=3.5, hip=(1.5, -22), lean=-2, ff=(-7.5, -2.4), bf=(7, -2.4), fh=(-13, 0), wa=90, bh=(-2, -5), be=1,
              drawn=True, arrow=True, cape=0.5)
    a2 = dict(fsh_fwd=3.5, hip=(1.5, -22), lean=-2, ff=(-7.5, -2.4), bf=(7, -2.4), fh=(-13, 0), wa=90, bh=(2, -5), be=1,
              drawn=False, cape=1)
    a3 = dict(fsh_fwd=3.5, hip=(1.5, -22), lean=-1, ff=(-7.5, -2.4), bf=(7, -2.4), fh=(-12, 1.5), wa=88, bh=(2.5, -2), be=1,
              cape=1)
    a4 = P(idle1)
    c0 = dict(fsh_fwd=3.5, hip=(0, -15), lean=6, ff=(-7, -2.4), bf=(9, -3.0, -35), bk=1, fh=(-13, -1), wa=90, bh=(-2, -5), be=1,
              drawn=True, arrow=True, cape=1)
    c1 = P(c0)
    c2 = dict(fsh_fwd=3.5, hip=(0, -15), lean=4, ff=(-7, -2.4), bf=(9, -3.0, -35), fh=(-13, -1), wa=90, bh=(2, -5), be=1,
              drawn=False, cape=2)
    c3 = P(c2, bh=(2.5, -2))
    c4 = P(idle1)
    d0 = dict(hip=(6, -23), lean=-8, ff=(-1, -3.5, 15), bf=(10, -2.4), fh=(-5, 8), wa=100, bh=(3, 9), cape=-2)
    d1 = dict(hip=(10, -22), lean=-14, ff=(2, -2.4), bf=(13, -2.4), fh=(-4, 7), wa=105, bh=(4, 8), cape=-3)
    h0 = dict(hip=(4, -21.5), lean=-14, ff=(-5, -2.4), bf=(9, -2.4), fh=(-2, 7), wa=120, bh=(5, 5), head=(1, 1),
              hv='hurt', cape=-2)
    A = {
        'idle': [(idle, 30), (idle1, 30)],
        'attack': [(a0, 12), (a1, 18), (a2, 4), (a3, 14), (a4, 8)],
        'crit': [(c0, 12), (c1, 22), (c2, 4), (c3, 18), (c4, 10)],
        'dodge': [(d0, 6), (d1, 16)],
        'hurt': [(h0, 12)],
    }
    E = {'attack': {'shoot': 2}, 'crit': {'shoot': 2}}
    A = finish(A, s)
    # 必杀：箭尖闪光
    A['crit'][1][0]['arrow_glint'] = True
    return A, E


def anims_magic(s=1.0):
    idle = dict(hip=(0, -22), lean=4, ff=(-6, -2.4), bf=(6, -2.4), bh=(-4, 6), wa=120, fh=(1.5, 10), cape=0)
    idle1 = P(idle, hip=(0, -21), lean=5, bh=(-4, 6.5), fh=(1.5, 10.5), cape=0.5)
    a0 = dict(hip=(0, -22), lean=2, ff=(-6.5, -2.4), bf=(6, -2.4), bh=(-6, 4), wa=95, book_open=True, fh=(-3, 3),
              cape=1)
    a1 = dict(hip=(0.5, -22.5), lean=-2, ff=(-6.5, -2.4), bf=(6.5, -2.4), bh=(-6, 4), wa=95, book_open=True,
              fh=(-2, -7), spark='small', cape=2, arm_behind_head=True)
    a2 = dict(hip=(-3, -21.5), lean=10, ff=(-9, -2.4), bf=(6, -2.4), bh=(-5, 5), wa=100, book_open=True, fh=(-10, 0),
              spark='big', cape=4)
    a3 = P(a2, spark=None, fh=(-9.5, 0.5), cape=3)
    a4 = P(idle1)
    c0 = dict(hip=(0, -22.5), lean=-4, ff=(-7, -2.4), bf=(7, -2.4), bh=(-3, -6), wa=150, book_open=True, fh=(-6, -4),
              spark='small', cape=3, back_arm_front=True)
    c1 = dict(hip=(0, -23), lean=-6, ff=(-7, -2.4), bf=(7, -2.4), bh=(-3, -7), wa=150, book_open=True, fh=(-4, -9),
              spark='big', cape=5, back_arm_front=True, arm_behind_head=True)
    c2 = dict(hip=(-4, -21), lean=14, ff=(-10, -2.4), bf=(6, -2.4), bh=(-5, 4), wa=100, book_open=True, fh=(-11, -1),
              spark='big', cape=6)
    c3 = P(c2, spark=None, cape=4)
    c4 = P(idle1)
    d0 = dict(hip=(6, -23), lean=-8, ff=(-1, -3.5, 15), bf=(10, -2.4), bh=(-3, 6), wa=120, fh=(2, 9), cape=-2)
    d1 = dict(hip=(10, -22), lean=-14, ff=(2, -2.4), bf=(13, -2.4), bh=(-2, 5), wa=125, fh=(3, 8), cape=-3)
    h0 = dict(hip=(4, -21.5), lean=-14, ff=(-5, -2.4), bf=(9, -2.4), bh=(-1, 5), wa=140, fh=(4, 6), head=(1, 1),
              hv='hurt', cape=-2)
    A = {
        'idle': [(idle, 32), (idle1, 32)],
        'attack': [(a0, 10), (a1, 14), (a2, 6), (a3, 16), (a4, 10)],
        'crit': [(c0, 16), (c1, 20), (c2, 6), (c3, 18), (c4, 10)],
        'dodge': [(d0, 6), (d1, 16)],
        'hurt': [(h0, 12)],
    }
    return finish(A, s), {'attack': {'spell': 2}, 'crit': {'spell': 2}}


def anims_staff(s=1.0):
    idle = dict(hip=(0, -22), lean=3, ff=(-5.5, -2.4), bf=(5.5, -2.4), fh=(-9, 9), wa=172, bh=(-2, 8), cape=0)
    idle1 = P(idle, hip=(0, -21), lean=4, fh=(-9, 9.5), bh=(-2, 8.5), cape=0.5)
    s0 = dict(hip=(-0.5, -22), lean=4, ff=(-6, -2.4), bf=(5.5, -2.4), fh=(-9, 1), wa=165, bh=(-3, 6), cape=1)
    s1 = dict(hip=(0, -22.5), lean=-2, ff=(-6, -2.4), bf=(6, -2.4), fh=(-7, -5), wa=170, bh=(-2, 3), glint=True,
              cape=2)
    s2 = P(s1, glint='small', cape=1.5)
    s3 = P(idle1)
    d0 = dict(hip=(6, -23), lean=-8, ff=(-1, -3.5, 15), bf=(10, -2.4), fh=(-6, 8), wa=165, bh=(0, 8), cape=-2)
    d1 = dict(hip=(10, -22), lean=-14, ff=(2, -2.4), bf=(13, -2.4), fh=(-5, 7.5), wa=160, bh=(1, 7), cape=-3)
    h0 = dict(hip=(4, -21.5), lean=-14, ff=(-5, -2.4), bf=(9, -2.4), fh=(2, 6), wa=150, bh=(3, 6), head=(1, 1),
              hv='hurt', cape=-2)
    A = {
        'idle': [(idle, 32), (idle1, 32)],
        'staff': [(s0, 12), (s1, 20), (s2, 16), (s3, 10)],
        'dodge': [(d0, 6), (d1, 16)],
        'hurt': [(h0, 12)],
    }
    return finish(A, s), {'staff': {'heal': 1}}


def anims_civilian(s=1.0):
    idle = dict(hip=(0, -20.5), lean=14, ff=(-5, -2.4), bf=(5, -2.4), fh=(-6, 8), wa=14, bh=(-2, 9), head=(0, 0.5))
    idle1 = P(idle, hip=(0, -20), lean=15, fh=(-6, 8.3), bh=(-2, 9.5))
    d0 = dict(hip=(4, -20.5), lean=4, ff=(-2, -2.4), bf=(8, -2.4), fh=(-5, 7), wa=20, bh=(1, 6), head=(0.5, 0))
    d1 = dict(hip=(7, -20.5), lean=-2, ff=(0, -2.4), bf=(10, -2.4), fh=(-4, 6), wa=25, bh=(2, 5), head=(1, 0))
    h0 = dict(hip=(3, -20), lean=0, ff=(-4, -2.4), bf=(7, -2.4), fh=(-3, 6), wa=30, bh=(2, 5), head=(1, 1), hv='hurt')
    A = {
        'idle': [(idle, 36), (idle1, 36)],
        'dodge': [(d0, 8), (d1, 16)],
        'hurt': [(h0, 12)],
    }
    return finish(A, s), {}


# ============================================================ 注册表
def _m(dash, typ, ranged=None, spell=None):
    return dict(dash=dash, type=typ, ranged=ranged, spell=spell)


SETS = {
    'elwin': dict(look=look_elwin, anims=lambda: anims_sword(1.0), meta=_m(True, 'melee')),
    'nora': dict(look=look_nora, anims=lambda: anims_bow(0.96), meta=_m(False, 'bow')),
    'serin': dict(look=look_serin, anims=lambda: anims_staff(0.95), meta=_m(False, 'staff')),
    'doran': dict(look=look_doran, anims=lambda: anims_armor(1.06, 'lance'), meta=_m(True, 'melee', 'javelin')),
    'sid': dict(look=look_sid, anims=lambda: anims_dagger(0.97), meta=_m(True, 'melee')),
    'mira': dict(look=look_mira, anims=lambda: anims_magic(0.92), meta=_m(False, 'magic', spell='fire')),
    'soldier': dict(look=look_soldier, anims=lambda: anims_lance(1.0), meta=_m(True, 'melee', 'javelin')),
    'fighter': dict(look=look_fighter, anims=lambda: anims_axe(1.04), meta=_m(True, 'melee', 'handaxe')),
    'mercenary': dict(look=look_mercenary, anims=lambda: anims_sword(1.0), meta=_m(True, 'melee')),
    'archer': dict(look=look_archer, anims=lambda: anims_bow(1.0), meta=_m(False, 'bow')),
    'mage_e': dict(look=look_mage_e, anims=lambda: anims_magic(1.0), meta=_m(False, 'magic', spell='thunder')),
    'darkmage': dict(look=look_darkmage, anims=lambda: anims_magic(1.0), meta=_m(False, 'magic', spell='dark')),
    'knight_e': dict(look=look_knight_e, anims=lambda: anims_armor(1.06, 'lance'), meta=_m(True, 'melee', 'javelin')),
    'priest': dict(look=look_priest, anims=lambda: anims_staff(1.0), meta=_m(False, 'staff')),
    'general': dict(look=look_general, anims=lambda: anims_armor(1.12, 'axe'), meta=_m(True, 'melee', 'handaxe')),
    'gord': dict(look=look_gord, anims=lambda: anims_axe(1.1), meta=_m(True, 'melee', 'handaxe')),
    'hagen': dict(look=lambda: look_general('hagen'), anims=lambda: anims_armor(1.12, 'lance'),
                  meta=_m(True, 'melee', 'javelin')),
    'morgan': dict(look=lambda: look_darkmage(True), anims=lambda: anims_magic(1.07), meta=_m(False, 'magic', spell='dark')),
    'valder': dict(look=look_valder, anims=lambda: anims_sword(1.1, heavy=True, ranged=True), meta=_m(True, 'melee', 'javelin')),
    'martha': dict(look=look_martha, anims=lambda: anims_civilian(0.88), meta=_m(False, 'none')),
}


def adjust(A, table):
    """按 (动画, 帧号) 微调坐骑姿势：dx/dy 平移坐骑（y 正 = 向下），其余键覆盖坐骑或骑手参数。"""
    import copy
    for (an, i), adj in table.items():
        if an not in A or i >= len(A[an]):
            continue
        pose, dur = A[an][i]
        pose = copy.deepcopy(pose)
        m, r = pose['m'], pose['r']
        x, y = m.get('pos', (0, 0))
        m['pos'] = (x + adj.get('dx', 0), y + adj.get('dy', 0))
        for k, v in adj.items():
            if k in ('dx', 'dy'):
                continue
            if k.startswith('r_'):
                r[k[2:]] = v
            else:
                m[k] = v
        A[an][i] = (pose, dur)
    return A


# ============================================================ 骑兵 / 天马 / 飞龙
import battle_mount as BM


def look_glenn():
    L = base_look('skin', 'hair_grey', 'eye_grey', body=BODY_BIG, scale=0.96)
    steel = metal('steel')
    green = mat('cloth_green')
    L.update(tunic=steel, sleeve=steel, forearm=steel, pants=steel, boots=dark_of('leather', 1), glove=mat('leather'),
             boot_top=0.6, knee_pad=steel)
    L['head'] = head('glenn')
    L['torso_extra'] = [
        cape_fn(green, length=6.0, width=1.1, hem=metal('gold')),
        emblem_fn(["yy", "yy"], {'y': GD[4]}, where=(3.2, 10.0), z=Z_TORSO + 3),
        belt_fn(mat('leather'), buckle=metal('gold')),
        BP.shield_fn(green, 'kite', size=1.0, z=Z_TORSO + 8, arm='b', rim=metal('gold'),
                     emblem=shield_emblem(["y.y", ".y.", "yyy"], {'y': GD[4]})),
    ]
    L['extra'] = [pauldron_fn(steel, 1.2)]
    L['weapon'] = dict(kind='lance', back=12, len=20, head_len=6)
    L['alt'] = dict(javelin=dict(kind='lance', back=5, len=12, head_len=5, head_w=1.6))
    L['mount'] = 'horse'
    L['mount_look'] = dict(coat=mat('leather', hi=0.4), mane=dark_of('hair_brown', 1), hoof=mat('iron'),
                           cloth=mat('cloth_navy'), cloth_trim=metal('gold'), saddle=dark_of('leather', 1),
                           bridle=dark_of('leather', 1), size=1.25)
    return L


HSTD = dict(nf=(0, 0, 18), ff=(-4, -2, 16), nh=(-22, 8, 16), fh=(-16, 4, 14))


def anims_cavalry(s=1.0):
    def M(**kw):
        d = dict(pos=(0, -37.5), pitch=0, neck=0, head=0, tail=0, legs=dict(HSTD))
        d.update(kw)
        return d

    def R(**kw):
        d = dict(lean=2, fh=(-6, 7), wa=100, bh=(-6, 6), cape=1)
        d.update(kw)
        return d
    idle = dict(m=M(), r=R())
    idle1 = dict(m=M(neck=2, head=4, tail=6), r=R(hip_off=(0, 0.6), fh=(-6, 7.5), cape=1.4))
    rear_legs = dict(nf=(70, -40, 10), ff=(60, -50, 5), nh=(-10, 12, 20), fh=(-4, 10, 18))
    lunge_legs = dict(nf=(60, 30, 40), ff=(45, 20, 30), nh=(-50, -30, -10), fh=(-42, -22, -6))
    a0 = dict(m=M(pos=(2, -38.5), pitch=7, neck=-4, legs=rear_legs, tail=10), r=R(lean=-6, fh=(0, 6), wa=100, cape=2))
    a1 = dict(m=M(pos=(-5, -36.5), pitch=-6, neck=6, head=6, legs=lunge_legs, tail=-10),
              r=R(lean=16, fh=(-11, 3), wa=94, thrust=12, cape=5))
    a2 = dict(m=M(pos=(-5, -36.5), pitch=-5, neck=5, head=5, legs=lunge_legs, tail=-8),
              r=R(lean=15, fh=(-10.5, 3.5), wa=95, cape=5))
    a3 = dict(m=M(pos=(-3, -37.5), pitch=0, tail=4), r=R(lean=6, cape=3))
    c0 = dict(m=M(pos=(4, -39.5), pitch=20, neck=-12, head=-8, legs=dict(nf=(95, -55, -10), ff=(85, -65, -15),
                                                                      nh=(-4, 6, 16), fh=(2, 8, 16)), tail=18),
              r=R(lean=-12, fh=(-3, -5), wa=128, glint=True, cape=3, arm_behind_head=True))
    c1 = dict(m=M(pos=(-7, -36), pitch=-9, neck=8, head=8, legs=lunge_legs, tail=-14),
              r=R(lean=20, fh=(-12, 2), wa=93, thrust=16, cape=7))
    c2 = dict(m=M(pos=(-7, -36), pitch=-8, neck=7, head=7, legs=lunge_legs, tail=-12),
              r=R(lean=19, fh=(-11.5, 2.5), wa=94, cape=7))
    c3 = P(a3)
    r0 = dict(m=M(neck=-3), r=R(lean=-6, fh=(4, -6), wa=115, wpn='javelin', arm_behind_head=True, cape=2))
    r1 = dict(m=M(neck=3, head=3), r=R(lean=14, fh=(-10, -1), wa=None, cape=4))
    r2 = dict(m=M(neck=3, head=3), r=R(lean=12, fh=(-7, 6), wa=None, cape=4))
    r3 = dict(m=M(), r=R(fh=(-5, 8), wa=None))
    d0 = dict(m=M(pos=(6, -38.5), pitch=8, neck=-6, legs=rear_legs, tail=10), r=R(lean=-8, cape=-1))
    d1 = dict(m=M(pos=(9, -37.5), pitch=3, neck=-3, tail=6), r=R(lean=-10, cape=-2))
    h0 = dict(m=M(pos=(3, -38), pitch=4, neck=-10, head=-10, tail=12), r=R(lean=-12, head=(1, 1), hv='hurt',
                                                                            fh=(-3, 6), cape=-1))
    A = {
        'idle': [(idle, 30), (idle1, 30)],
        'attack': [(a0, 14), (a1, 4), (a2, 16), (a3, 10)],
        'crit': [(c0, 24), (c1, 4), (c2, 22), (c3, 10)],
        'ranged': [(r0, 16), (r1, 4), (r2, 14), (r3, 8)],
        'dodge': [(d0, 8), (d1, 14)],
        'hurt': [(h0, 12)],
    }
    adjust(A, {('crit', 0): dict(dy=2), ('crit', 1): dict(dx=4), ('crit', 2): dict(dx=3)})
    return A, {'attack': {'hit': 1}, 'crit': {'hit': 1}, 'ranged': {'shoot': 1}}


SETS['glenn'] = dict(look=look_glenn, anims=lambda: anims_cavalry(1.0), meta=_m(True, 'melee', 'javelin'),
                     builder=BM.build_mounted)


def look_vera():
    L = base_look('skin', 'hair_silver', 'eye_ice', body=BODY_F, scale=0.95)
    sky = mat('cloth_sky')
    white = mat('cloth_white')
    L.update(tunic=sky, sleeve=white, forearm=white, pants=white, boots=white, glove=white, boot_top=0.6)
    L['head'] = head('vera')
    L['torso_extra'] = [
        cape_fn(mat('cloth_sky'), length=5.0, width=1.0, hem=white),
        poly_local([(4.4, 5.0), (4.6, 9.3), (3.4, 12.0), (-0.4, 12.4), (-2.4, 10.4), (-2.6, 6.6), (-0.8, 4.2)],
                   metal('cloth_white', spec=CW[4]), Z_TORSO + 1, 'plate', sigma=1.2),
        skirt_fn(sky, length=5.5, lining=white),
        belt_fn(white, buckle=metal('gold')),
    ]
    L['extra'] = [pauldron_fn(white, 0.95), BP.ponytail_fn(mat('hair_silver'), root=(4.2, -7.5),
                                                           segs=((-35, 4.5, 2.1), (-20, 5.0, 1.8), (-8, 5.0, 1.3)),
                                                           tie=mat('cloth_sky'))]
    L['weapon'] = dict(kind='lance', back=11, len=19, head_len=6, tassel=mat('cloth_sky'))
    L['alt'] = dict(javelin=dict(kind='lance', back=5, len=12, head_len=5, head_w=1.6))
    L['mount'] = 'pegasus'
    L['mount_look'] = dict(coat=Mat('cloth_white', hi=0.5), mane=mat('cloth_sky'), hoof=metal('gold'),
                           wing=Mat('cloth_white', hi=0.45, sh=-0.2), size=1.18, saddle=mat('cloth_sky'),
                           bridle=metal('gold'), wing_len=36)
    return L


def look_cavalier_e():
    L = base_look('skin', 'hair_black', 'eye_brown', body=BODY_BIG, scale=0.96)
    iron = metal('iron', spec=IR[4])
    red = mat('cloth_crimson')
    L.update(tunic=iron, sleeve=iron, forearm=iron, pants=iron, boots=dark_of('leather', 1), glove=mat('leather'),
             boot_top=0.6, knee_pad=iron)
    L['head'] = head('cavalier_e')
    L['torso_extra'] = [
        cape_fn(red, length=6.0, width=1.1),
        poly_local([(5.8, 1.0), (6.2, 9.6), (4.4, 13.0), (-2.0, 13.4), (-3.4, 9.0), (-2.6, 1.0)], red,
                   Z_TORSO + 1, 'tabard', sigma=1.3),
        emblem_fn(EAGLE_S, {'b': BK[1]}, where=(2.6, 8.2), group='tabard_em'),
        belt_fn(mat('leather'), buckle=metal('iron')),
        BP.shield_fn(red, 'kite', size=1.0, z=Z_TORSO + 8, arm='b', rim=iron,
                     emblem=shield_emblem(EAGLE_S, {'b': BK[1]})),
    ]
    L['extra'] = [pauldron_fn(iron, 1.2)]
    L['weapon'] = dict(kind='lance', back=12, len=20, head_len=6)
    L['alt'] = dict(javelin=dict(kind='lance', back=5, len=12, head_len=5, head_w=1.6))
    L['mount'] = 'horse'
    L['mount_look'] = dict(coat=Mat(None, hi=0.3, sh=-0.25, tones=[BK[0], BK[1], BK[2], BK[3],
                                                                   PAL['cloth_brown'][2]]),
                           mane=mat('cloth_black'), hoof=mat('iron'), cloth=mat('cloth_crimson'),
                           cloth_trim=metal('iron'), saddle=dark_of('leather', 1), bridle=metal('iron'), size=1.25)
    return L


def look_pegasus_e():
    L = base_look('skin', 'hair_blonde', 'eye_ice', body=BODY_F, scale=0.95)
    steel = metal('steel')
    teal = dark_of('cloth_teal', 0)
    L.update(tunic=teal, sleeve=steel, forearm=steel, pants=mat('cloth_brown'), boots=dark_of('leather', 1),
             glove=mat('leather'), boot_top=0.6)
    L['head'] = head('pegasus_e')
    fur = Mat('hair_grey', hi=0.4)
    L['torso_extra'] = [
        cape_fn(dark_of('cloth_teal', 1), length=5.0, width=1.0),
        poly_local([(4.4, 5.0), (4.6, 9.3), (3.4, 12.0), (-0.4, 12.4), (-2.4, 10.4), (-2.6, 6.6), (-0.8, 4.2)],
                   steel, Z_TORSO + 1, 'plate', sigma=1.2),
        skirt_fn(teal, length=5.5),
        belt_fn(mat('leather'), buckle=metal('iron')),
        BP.mantle_fn(fur, size=0.85),
    ]
    L['extra'] = [BP.ponytail_fn(mat('hair_blonde'), root=(4.0, -6.5), segs=((-25, 3.5, 1.8), (-10, 4.0, 1.4)))]
    L['weapon'] = dict(kind='lance', back=11, len=19, head_len=6)
    L['alt'] = dict(javelin=dict(kind='lance', back=5, len=12, head_len=5, head_w=1.6))
    L['mount'] = 'pegasus'
    L['mount_look'] = dict(coat=Mat('cloth_white', hi=0.5), mane=mat('hair_silver'), hoof=mat('iron'),
                           wing=Mat('cloth_white', hi=0.45, sh=-0.2), size=1.18, saddle=dark_of('leather', 1),
                           bridle=metal('iron'), wing_len=36)
    return L


FLY_LEGS = dict(nf=(70, -25, -35), ff=(58, -32, -40), nh=(-62, -38, -25), fh=(-52, -32, -20))


def anims_pegasus(s=1.0):
    def M(**kw):
        d = dict(pos=(0, -31), pitch=0, neck=0, head=0, tail=-12, wing=0.6, spread=1.0, legs=dict(FLY_LEGS))
        d.update(kw)
        return d

    def R(**kw):
        d = dict(lean=2, fh=(-6, 7), wa=100, bh=(-2, 9), cape=2)
        d.update(kw)
        return d
    idle = dict(m=M(), r=R())
    idle1 = dict(m=M(pos=(0, -29), wing=-0.5, tail=-6, mane=1.0), r=R(cape=2.6, hair=0.4))
    a0 = dict(m=M(pos=(2, -34), pitch=10, wing=0.85, tail=-4), r=R(lean=-6, fh=(0, 5), wa=100, cape=3))
    a1 = dict(m=M(pos=(-6, -27), pitch=-12, neck=8, head=6, wing=-0.6, tail=-20),
              r=R(lean=18, fh=(-11, 3), wa=92, thrust=12, cape=6))
    a2 = dict(m=M(pos=(-6, -27), pitch=-10, neck=7, head=5, wing=-0.2, tail=-18),
              r=R(lean=16, fh=(-10.5, 3.5), wa=93, cape=6))
    a3 = dict(m=M(pos=(-3, -30), wing=0.6), r=R(lean=6, cape=4))
    c0 = dict(m=M(pos=(4, -36), pitch=18, neck=-10, head=-6, wing=0.9, tail=0),
              r=R(lean=-10, fh=(-3, -5), wa=128, glint=True, cape=3, arm_behind_head=True))
    c1 = dict(m=M(pos=(-8, -25), pitch=-16, neck=10, head=8, wing=-0.8, tail=-24),
              r=R(lean=22, fh=(-12, 2), wa=91, thrust=16, cape=7))
    c2 = dict(m=M(pos=(-8, -25), pitch=-14, neck=9, head=7, wing=-0.3, tail=-22),
              r=R(lean=20, fh=(-11.5, 2.5), wa=92, cape=7))
    c3 = P(a3)
    r0 = dict(m=M(wing=1.0), r=R(lean=-6, fh=(4, -6), wa=115, wpn='javelin', arm_behind_head=True, cape=3))
    r1 = dict(m=M(wing=-0.5, pitch=-4), r=R(lean=14, fh=(-10, -1), wa=None, cape=5))
    r2 = dict(m=M(wing=0.2, pitch=-3), r=R(lean=12, fh=(-7, 6), wa=None, cape=4))
    r3 = dict(m=M(), r=R(fh=(-5, 8), wa=None))
    d0 = dict(m=M(pos=(6, -37), pitch=12, neck=-6, wing=0.85, tail=-2), r=R(lean=-8, cape=0))
    d1 = dict(m=M(pos=(9, -34), pitch=6, wing=-0.4, tail=-8), r=R(lean=-10, cape=-1))
    h0 = dict(m=M(pos=(3, -30), pitch=8, neck=-12, head=-10, wing=0.2, tail=-4),
              r=R(lean=-12, head=(1, 1), hv='hurt', fh=(-3, 6), cape=0))
    A = {
        'idle': [(idle, 20), (idle1, 20)],
        'attack': [(a0, 14), (a1, 4), (a2, 16), (a3, 10)],
        'crit': [(c0, 24), (c1, 4), (c2, 22), (c3, 10)],
        'ranged': [(r0, 16), (r1, 4), (r2, 14), (r3, 8)],
        'dodge': [(d0, 8), (d1, 14)],
        'hurt': [(h0, 12)],
    }
    adjust(A, {('attack', 0): dict(dy=2, wing=0.55), ('attack', 1): dict(dy=-3), ('attack', 2): dict(dy=-2),
               ('crit', 0): dict(dy=2, wing=0.6), ('crit', 1): dict(dx=4, dy=-5), ('crit', 2): dict(dx=4, dy=-5),
               ('ranged', 0): dict(dy=3, wing=0.5), ('dodge', 0): dict(dy=4, wing=0.6), ('dodge', 1): dict(dx=-2),
               ('hurt', 0): dict(dy=-2)})
    return A, {'attack': {'hit': 1}, 'crit': {'hit': 1}, 'ranged': {'shoot': 1}}


def look_wyvern(boss=False):
    if boss:
        L = base_look('skin', 'hair_blonde', 'eye_ice', body=BODY_BIG, scale=1.0)
    else:
        L = base_look('skin', 'hair_brown', 'eye_grey', body=BODY_BIG, scale=0.95)
    steel = metal('steel')
    fur = Mat('hair_grey', hi=0.4)
    teal = dark_of('cloth_teal', 1)
    L.update(tunic=steel, sleeve=steel, forearm=steel, pants=mat('cloth_brown'), boots=dark_of('leather', 1),
             glove=mat('leather'), boot_top=0.6, knee_pad=steel)
    L['head'] = head('grimm' if boss else 'wyvern')
    L['torso_extra'] = [
        cape_fn(fur if boss else teal, length=6.0, width=1.15),
        poly_local([(5.8, 1.0), (6.2, 9.6), (4.4, 13.0), (-2.0, 13.4), (-3.4, 9.0), (-2.6, 1.0)], teal,
                   Z_TORSO + 1, 'tabard', sigma=1.3),
        belt_fn(mat('leather'), buckle=metal('iron')),
        BP.mantle_fn(fur, size=1.1 if boss else 0.9),
    ]
    L['extra'] = [pauldron_fn(steel, 1.2)]
    if boss:
        L['weapon'] = dict(kind='axe', back=4, len=17, head_size=1.2)
        L['alt'] = dict(handaxe=dict(kind='handaxe'))
    else:
        L['weapon'] = dict(kind='lance', back=12, len=20, head_len=6)
        L['alt'] = dict(javelin=dict(kind='lance', back=5, len=12, head_len=5, head_w=1.6))
    L['mount'] = 'wyvern'
    if boss:
        scale_m = Mat(None, tones=[PAL['stone'][0], PAL['stone'][1], PAL['stone'][2], PAL['stone'][3],
                                   PAL['stone'][4]], hi=0.3)
        wing = Mat(None, tones=[PAL['cloth_purple'][0], PAL['cloth_purple'][1], PAL['cloth_purple'][2],
                                PAL['stone'][2], PAL['stone'][3]], hi=0.5)
        eye = PAL['eye_red'][3]
    else:
        scale_m = Mat('forest', hi=0.35)
        wing = Mat(None, tones=[PAL['forest'][0], PAL['forest'][1], PAL['cloth_olive'][2], PAL['cloth_olive'][3],
                                PAL['cloth_olive'][4]], hi=0.5)
        eye = PAL['eye_gold'][3]
    L['mount_look'] = dict(scale=scale_m, belly=Mat('rock', off=1, hi=0.4), wing=wing, horn=mat('cloth_white'),
                           eye=eye, size=1.3)
    return L


def anims_wyvern(s=1.0, weapon='lance'):
    def M(**kw):
        d = dict(pos=(0, -32), pitch=0, neck=0, head=0, tail=0, wing=0.55, jaw=0)
        d.update(kw)
        return d

    def R(**kw):
        d = dict(lean=4, fh=(-6, 7), wa=100, bh=(-2, 9), cape=2, foot_ang=10)
        d.update(kw)
        return d
    if weapon == 'lance':
        rid = R()
        idle = dict(m=M(), r=rid)
        idle1 = dict(m=M(pos=(0, -30), wing=-0.4, tail=6, neck=3), r=R(cape=2.5))
        a0 = dict(m=M(pos=(2, -35), pitch=8, wing=0.85, neck=-6), r=R(lean=-6, fh=(0, 5), cape=3))
        a1 = dict(m=M(pos=(-7, -29), pitch=-10, wing=-0.7, neck=8, head=6, tail=-10),
                  r=R(lean=18, fh=(-11, 3), wa=92, thrust=12, cape=6))
        a2 = dict(m=M(pos=(-7, -29), pitch=-8, wing=-0.2, neck=7, head=5, tail=-8),
                  r=R(lean=16, fh=(-10.5, 3.5), wa=93, cape=6))
        a3 = dict(m=M(pos=(-4, -32)), r=R(lean=6, cape=4))
        c0 = dict(m=M(pos=(2, -36), pitch=10, wing=0.9, neck=-14, head=-12, jaw=3.0, tail=10),
                  r=R(lean=-10, fh=(-3, -5), wa=128, glint=True, cape=3, arm_behind_head=True))
        c1 = dict(m=M(pos=(-9, -28), pitch=-14, wing=-0.9, neck=10, head=8, jaw=2.0, tail=-14),
                  r=R(lean=22, fh=(-12, 2), wa=91, thrust=16, cape=7))
        c2 = dict(m=M(pos=(-9, -28), pitch=-12, wing=-0.3, neck=9, head=7, tail=-12),
                  r=R(lean=20, fh=(-11.5, 2.5), wa=92, cape=7))
        attack = [(a0, 14), (a1, 4), (a2, 16), (a3, 10)]
        crit = [(c0, 24), (c1, 4), (c2, 22), (dict(m=M(pos=(-4, -32)), r=R(lean=6, cape=4)), 10)]
        ev = {'attack': {'hit': 1}, 'crit': {'hit': 1}}
        rw = 'javelin'
        rwa = 115
    else:
        rid = R(fh=(-6, 6), wa=130)
        idle = dict(m=M(), r=rid)
        idle1 = dict(m=M(pos=(0, -30), wing=-0.4, tail=6, neck=3), r=R(fh=(-6, 6.5), wa=128, cape=2.5))
        a0 = dict(m=M(pos=(1, -34), pitch=6, wing=1.0, neck=-4), r=R(lean=-4, fh=(1, -8), wa=-150,
                                                                   arm_behind_head=True, cape=3))
        a1 = dict(m=M(pos=(2, -34), pitch=8, wing=0.9, neck=-6), r=R(lean=-10, fh=(4, -5), wa=-115, wz=Z_TORSO - 1,
                                                                   arm_behind_head=True, cape=3))
        a2 = dict(m=M(pos=(-7, -29), pitch=-10, wing=-0.7, neck=8, head=6, tail=-10),
                  r=R(lean=26, fh=(-9, 6), wa=55, smear=(-115, -305, 1.6), cape=6))
        a3 = dict(m=M(pos=(-7, -29), pitch=-8, wing=-0.3, neck=7, head=5, tail=-8),
                  r=R(lean=28, fh=(-6, 10), wa=28, cape=6))
        a4 = dict(m=M(pos=(-4, -32)), r=R(fh=(-6, 6), wa=130, cape=4))
        c0 = dict(m=M(pos=(2, -36), pitch=10, wing=0.9, neck=-14, head=-12, jaw=3.0, tail=10),
                  r=R(lean=-6, fh=(0, -7), wa=172, glint=True, arm_behind_head=True, cape=3))
        c1 = dict(m=M(pos=(-9, -28), pitch=-14, wing=-0.9, neck=10, head=8, jaw=2.0, tail=-14),
                  r=R(lean=30, fh=(-9, 7), wa=45, smear=(-160, -315, 2.0), cape=7))
        c2 = dict(m=M(pos=(-9, -28), pitch=-12, wing=-0.3, neck=9, head=7, tail=-12),
                  r=R(lean=32, fh=(-6, 10), wa=22, cape=7))
        attack = [(a0, 10), (a1, 12), (a2, 4), (a3, 18), (a4, 10)]
        crit = [(c0, 26), (c1, 4), (c2, 22), (a4, 10)]
        ev = {'attack': {'hit': 2}, 'crit': {'hit': 1}}
        rw = 'handaxe'
        rwa = -140
    r0 = dict(m=M(wing=1.0), r=R(lean=-6, fh=(4, -6), wa=rwa, wpn=rw, arm_behind_head=True, cape=3))
    r1 = dict(m=M(wing=-0.5, pitch=-4), r=R(lean=14, fh=(-10, -1), wa=None, cape=5))
    r2 = dict(m=M(wing=0.2, pitch=-3), r=R(lean=12, fh=(-7, 6), wa=None, cape=4))
    r3 = dict(m=M(), r=R(fh=(-5, 8), wa=None))
    d0 = dict(m=M(pos=(5, -38), pitch=10, wing=0.85, neck=-6), r=dict(rid, lean=-8, cape=0))
    d1 = dict(m=M(pos=(8, -35), pitch=5, wing=-0.4), r=dict(rid, lean=-10, cape=-1))
    h0 = dict(m=M(pos=(2, -32), pitch=8, neck=-14, head=-12, jaw=2.5, wing=0.3),
              r=dict(rid, lean=-12, head=(1, 1), hv='hurt', cape=0))
    A = {
        'idle': [(idle, 24), (idle1, 24)],
        'attack': attack,
        'crit': crit,
        'ranged': [(r0, 16), (r1, 4), (r2, 14), (r3, 8)],
        'dodge': [(d0, 8), (d1, 14)],
        'hurt': [(h0, 12)],
    }
    ev['ranged'] = {'shoot': 1}
    big = 2 if weapon != 'lance' else 0
    tab = {('idle', 0): dict(dy=3), ('idle', 1): dict(dy=3), ('attack', 0): dict(dy=4, wing=0.45),
           ('attack', 1): dict(dx=3 + big // 2, dy=2), ('attack', 2): dict(dx=2 + big // 2, dy=2), ('attack', 3): dict(dx=big, dy=3),
           ('crit', 0): dict(dy=1, wing=0.4, neck=-8, head=-6), ('crit', 1): dict(dx=7, dy=2, tail=12),
           ('crit', 2): dict(dx=7, dy=2, tail=12), ('crit', 3): dict(dx=big, dy=3),
           ('ranged', 0): dict(dy=4, wing=0.45), ('ranged', 1): dict(dy=3, dx=-1), ('ranged', 2): dict(dy=3, dx=-1),
           ('ranged', 3): dict(dy=3, dx=-1),
           ('dodge', 0): dict(dy=7, wing=0.45), ('dodge', 1): dict(dx=-4, dy=3), ('hurt', 0): dict(dy=3)}
    if weapon != 'lance':
        tab[('attack', 4)] = dict(dx=2, dy=3)
        tab[('attack', 0)] = dict(dy=4, wing=0.45, r_fh=(1, -5))
        tab[('attack', 1)] = dict(dy=4, wing=0.45, r_fh=(4, -3))
        tab[('crit', 0)] = dict(dy=1, wing=0.4, neck=-8, head=-6, r_fh=(1, -4), r_wa=165)
        tab[('crit', 1)] = dict(dx=5, dy=2, tail=12)
        tab[('crit', 2)] = dict(dx=5, dy=2, tail=12)
        tab[('crit', 3)] = dict(dx=2, dy=3)
    adjust(A, tab)
    return A, ev


SETS['vera'] = dict(look=look_vera, anims=lambda: anims_pegasus(1.0), meta=_m(True, 'melee', 'javelin'),
                    builder=BM.build_mounted)
SETS['cavalier_e'] = dict(look=look_cavalier_e, anims=lambda: anims_cavalry(1.0), meta=_m(True, 'melee', 'javelin'),
                          builder=BM.build_mounted)
SETS['pegasus_e'] = dict(look=look_pegasus_e, anims=lambda: anims_pegasus(1.0), meta=_m(True, 'melee', 'javelin'),
                         builder=BM.build_mounted)
SETS['wyvern'] = dict(look=look_wyvern, anims=lambda: anims_wyvern(1.0, 'lance'), meta=_m(True, 'melee', 'javelin'),
                      builder=BM.build_mounted)
SETS['grimm'] = dict(look=lambda: look_wyvern(True), anims=lambda: anims_wyvern(1.0, 'axe'),
                     meta=_m(True, 'melee', 'handaxe'), builder=BM.build_mounted)
