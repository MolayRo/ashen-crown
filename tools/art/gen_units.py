# -*- coding: utf-8 -*-
"""
《灰烬王冠》地图小人精灵生成器 → assets/units.png + assets/units.json

  * 16 个模型 × 4 阵营（blue 我方 / red 敌方 / green 友军 / grey 已行动）× 15 帧
  * 每帧 32×32，锚点 [16, 31]（脚底中心）；帧名 {model}_{team}_{anim}{i}
  * 动画：idle 3 帧（播放 0-1-2-1）、down / up / side 各 4 帧；side 朝左，右走由程序镜像
    步兵 idle 朝镜头；骑马/飞行单位 idle 用侧面（朝左，FE 惯例）
  * 画法：字符画 + 材质角色（见 LEGEND）；阵营色只用于衣甲披风等大面积区域，
    发色/肤色/金属保持自然色；grey 阵营把其余材质按明度映射到冷灰色阶并压暗。
    剪影外描边由 compose() 自动补 INK；骑手/盾等叠在坐骑上的层用 outline=True 自带描边。
用法：python tools/art/gen_units.py [--preview]
"""
import os
import sys
import json

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from palette import PAL, INK, INK2, CLEAR  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
ASSETS = os.path.join(ROOT, 'assets')
PREV = os.path.join(HERE, 'preview', 'units')

FW = FH = 32
AX, AY = 16, 31
TEAMS = ['blue', 'red', 'green', 'grey']

# ---------------------------------------------------------------------------
# 字符图例：字符 -> (材质角色, 色阶序号)
# ---------------------------------------------------------------------------
LEGEND = {
    'o': ('ink', 0), 'O': ('ink2', 0),
    '0': ('team', 0), '1': ('team', 1), '2': ('team', 2), '3': ('team', 3), '4': ('team', 4), '5': ('team', 5),
    'K': ('skin', 0), 'k': ('skin', 1), 's': ('skin', 2), 'S': ('skin', 3), 'Z': ('skin', 4),
    'J': ('hair', 0), 'j': ('hair', 1), 'h': ('hair', 2), 'H': ('hair', 3), 'Y': ('hair', 4),
    'e': ('eye', 1), 'E': ('eye', 2),
    'N': ('metal', 0), 'n': ('metal', 1), 'm': ('metal', 2), 'M': ('metal', 3), 'W': ('metal', 4),
    'q': ('gold', 1), 'g': ('gold', 2), 'G': ('gold', 3), 'Q': ('gold', 4),
    'b': ('leather', 1), 'l': ('leather', 2), 'L': ('leather', 3), 'B': ('leather', 4),
    'u': ('cloth', 1), 'c': ('cloth', 2), 'C': ('cloth', 3), 'U': ('cloth', 4),
    'v': ('white', 1), 'w': ('white', 2), 'V': ('white', 3), 'X': ('white', 4),
    't': ('wood', 1), 'd': ('wood', 2), 'D': ('wood', 3), 'T': ('wood', 4),
    'p': ('mount', 1), 'a': ('mount', 2), 'A': ('mount', 3), 'P': ('mount', 4),
    'f': ('mane', 1), 'F': ('mane', 2), 'r': ('mane', 3), 'R': ('mane', 4),
    'i': ('dark', 1), 'x': ('dark', 2), 'y': ('dark', 3), 'z': ('dark', 4),
}

DEFAULT_MATS = {
    'skin': 'skin', 'hair': 'hair_brown', 'eye': 'eye_brown', 'metal': 'steel', 'gold': 'gold',
    'leather': 'leather', 'cloth': 'cloth_white', 'white': 'cloth_white', 'wood': 'wood',
    'mount': 'leather', 'mane': 'hair_brown', 'dark': 'cloth_black',
}


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


# 灰色（已行动）换色候选：只取调色板里的冷灰色阶
GREY_CANDS = []
for _k in ('team_grey', 'iron', 'stone', 'grey'):
    for _c in PAL[_k]:
        if _c not in GREY_CANDS and lum(_c) < 236:
            GREY_CANDS.append(_c)
GREY_CANDS.sort(key=lum)


def to_grey(c, role, rname):
    L = lum(c)
    if role == 'skin':
        L = L * 0.85 + 12          # 肤色保持偏亮，脸不糊
    elif role == 'hair' and lum(PAL[rname][3]) > 150:
        L = L * 0.52 + 4           # 浅发色压暗，与肤色拉开
    elif role == 'eye':
        L = 30
    else:
        L = L * 0.78 + 10
    return min(GREY_CANDS, key=lambda g: abs(lum(g) - L))


def resolve(ch, mats, team, extra=None):
    spec = extra[ch] if (extra and ch in extra) else LEGEND.get(ch)
    if spec is None:
        raise KeyError('unknown pixel char %r' % ch)
    role, idx = spec
    if role == 'ink':
        return INK
    if role == 'ink2':
        return INK2
    if role == 'team':
        r = PAL['team_' + team]
        return r[max(0, min(len(r) - 1, idx))]
    rname = mats.get(role, DEFAULT_MATS.get(role))
    r = PAL[rname]
    c = r[max(0, min(len(r) - 1, idx))]
    if team == 'grey':
        c = to_grey(c, role, rname)
    return c


ART_WARN = []


def art(s):
    lines = [ln.strip() for ln in s.strip('\n').split('\n')]
    lines = [ln for ln in lines if ln]
    ws = set(len(ln) for ln in lines)
    if len(ws) > 1:
        ART_WARN.append((sorted(ws), lines[0], [ln for ln in lines if len(ln) != len(lines[0])]))
    return lines


class Layer:
    """一层像素图：a 可以是字符串，或 {变体键: 字符串}。tag 决定跟随哪个部位位移。"""

    def __init__(self, a, x, y, tag='body', extra=None, outline=False):
        if isinstance(a, dict):
            self.arts = {k: (art(v) if isinstance(v, str) else v) for k, v in a.items()}
        elif isinstance(a, list):
            self.arts = {'base': a}
        else:
            self.arts = {'base': art(a)}
        self.x, self.y, self.tag, self.extra = x, y, tag, extra
        self.outline = outline      # True：本层自带一圈 INK 描边（压在下层之上）

    def pick(self, keys):
        for k in keys:
            if k in self.arts:
                return self.arts[k]
        return self.arts.get('base') or next(iter(self.arts.values()))


def compose(layers, keys, offs, mats, team):
    """keys: 本帧的变体键优先级列表；offs: {tag: (dx, dy)}"""
    grid = [[None] * FW for _ in range(FH)]
    for L in layers:
        rows = L.pick(keys)
        if rows is None:
            continue
        dx, dy = offs.get(L.tag, (0, 0))
        mine = set()
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch == '.' or ch == ' ':
                    continue
                X, Y = L.x + i + dx, L.y + j + dy
                if not (0 <= X < FW and 0 <= Y < FH):
                    continue
                if ch == ',':
                    grid[Y][X] = None
                    continue
                grid[Y][X] = resolve(ch, mats, team, L.extra)
                mine.add((X, Y))
        if L.outline:
            ring = set()
            for (X, Y) in mine:
                if grid[Y][X] in (INK, INK2):
                    continue
                for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    p = (X + ddx, Y + ddy)
                    if p not in mine and 0 <= p[0] < FW and 0 <= p[1] < FH:
                        ring.add(p)
            for (X, Y) in ring:
                grid[Y][X] = INK
    # 自动外描边：透明像素若与非描边色 4 邻接 -> INK
    outline = []
    for y in range(FH):
        for x in range(FW):
            if grid[y][x] is not None:
                continue
            for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                xx, yy = x + ddx, y + ddy
                if 0 <= xx < FW and 0 <= yy < FH:
                    c = grid[yy][xx]
                    if c is not None and c != INK and c != INK2:
                        outline.append((x, y))
                        break
    for x, y in outline:
        grid[y][x] = INK
    img = Image.new('RGBA', (FW, FH), CLEAR)
    px = img.load()
    for y in range(FH):
        for x in range(FW):
            if grid[y][x] is not None:
                px[x, y] = grid[y][x]
    return img


# ---------------------------------------------------------------------------
# 步兵通用动画
#   视图 front/back/side；head / body 两个位移组；腿按姿势换图
#   待机：0 原位 → 1 头低 1px → 2 头+身低 1px（播放 0-1-2-1）
#   行走：着地帧原位，交叉帧身体抬高 1px
# ---------------------------------------------------------------------------
FOOT_ANIMS = {
    'idle': [
        ('front', ['idle0', 'stand'], {'head': (0, 0), 'body': (0, 0)}),
        ('front', ['idle1', 'stand'], {'head': (0, 1), 'body': (0, 0)}),
        ('front', ['idle2', 'stand'], {'head': (0, 1), 'body': (0, 1)}),
    ],
    'down': [
        ('front', ['down0', 'stepA'], {'head': (0, 0), 'body': (0, 0)}),
        ('front', ['down1', 'pass'], {'head': (0, -1), 'body': (0, -1)}),
        ('front', ['down2', 'stepB'], {'head': (0, 0), 'body': (0, 0)}),
        ('front', ['down3', 'pass'], {'head': (0, -1), 'body': (0, -1)}),
    ],
    'up': [
        ('back', ['up0', 'stepA'], {'head': (0, 0), 'body': (0, 0)}),
        ('back', ['up1', 'pass'], {'head': (0, -1), 'body': (0, -1)}),
        ('back', ['up2', 'stepB'], {'head': (0, 0), 'body': (0, 0)}),
        ('back', ['up3', 'pass'], {'head': (0, -1), 'body': (0, -1)}),
    ],
    'side': [
        ('side', ['side0', 'strideA', 'swingA'], {'head': (0, 0), 'body': (0, 0)}),
        ('side', ['side1', 'passA', 'swingM'], {'head': (0, -1), 'body': (0, -1)}),
        ('side', ['side2', 'strideB', 'swingB'], {'head': (0, 0), 'body': (0, 0)}),
        ('side', ['side3', 'passB', 'swingM'], {'head': (0, -1), 'body': (0, -1)}),
    ],
}

# ---------------------------------------------------------------------------
# 骑乘单位动画（马）：待机用侧面（朝左），马头点头、尾巴甩；行走四帧换腿并起伏
#   位移组：mhead 马头颈 / mbody 马身+尾+鞍 / rider 骑手身体+武器 / rhead 骑手头
# ---------------------------------------------------------------------------
def _mo(mh=0, mb=0, r=0, rh=None):
    return {'mhead': (0, mh), 'mbody': (0, mb), 'rider': (0, r), 'rhead': (0, r if rh is None else rh)}


MOUNT_ANIMS = {
    'idle': [
        ('side', ['idle0', 'stand'], _mo()),
        ('side', ['idle1', 'stand'], _mo(mh=1)),
        ('side', ['idle2', 'stand', 'swish'], _mo(mh=1, r=1)),
    ],
    'side': [
        ('side', ['side0', 'w0'], _mo()),
        ('side', ['side1', 'w1'], _mo(mh=-1, mb=-1, r=-1)),
        ('side', ['side2', 'w2'], _mo()),
        ('side', ['side3', 'w3'], _mo(mh=-1, mb=-1, r=-1)),
    ],
    'down': [
        ('front', ['down0', 'w0'], _mo()),
        ('front', ['down1', 'w1'], _mo(mh=-1, mb=-1, r=-1)),
        ('front', ['down2', 'w2'], _mo()),
        ('front', ['down3', 'w3'], _mo(mh=-1, mb=-1, r=-1)),
    ],
    'up': [
        ('back', ['up0', 'w0'], _mo()),
        ('back', ['up1', 'w1'], _mo(mh=-1, mb=-1, r=-1)),
        ('back', ['up2', 'w2'], _mo()),
        ('back', ['up3', 'w3'], _mo(mh=-1, mb=-1, r=-1)),
    ],
}

# 飞行单位：翅膀 up/mid/down 三态，下扑时身体上浮
FLY_ANIMS = {
    'idle': [
        ('side', ['idle0', 'wup'], _mo()),
        ('side', ['idle1', 'wmid'], _mo(mh=1)),
        ('side', ['idle2', 'wdown'], _mo(mh=0, mb=-1, r=-1, rh=-1)),
    ],
    'side': [
        ('side', ['side0', 'wup'], _mo(mh=1, mb=1, r=1)),
        ('side', ['side1', 'wmid'], _mo()),
        ('side', ['side2', 'wdown'], _mo(mh=-1, mb=-1, r=-1)),
        ('side', ['side3', 'wmid'], _mo()),
    ],
    'down': [
        ('front', ['down0', 'wup'], _mo(mh=1, mb=1, r=1)),
        ('front', ['down1', 'wmid'], _mo()),
        ('front', ['down2', 'wdown'], _mo(mh=-1, mb=-1, r=-1)),
        ('front', ['down3', 'wmid'], _mo()),
    ],
    'up': [
        ('back', ['up0', 'wup'], _mo(mh=1, mb=1, r=1)),
        ('back', ['up1', 'wmid'], _mo()),
        ('back', ['up2', 'wdown'], _mo(mh=-1, mb=-1, r=-1)),
        ('back', ['up3', 'wmid'], _mo()),
    ],
}

ANIM_TABLES = {'foot': FOOT_ANIMS, 'mount': MOUNT_ANIMS, 'fly': FLY_ANIMS}

ANIM_ORDER = [('idle', 3), ('down', 4), ('up', 4), ('side', 4)]
IDLE_DUR = [32, 5, 32, 5]
WALK_DUR = [8, 7, 8, 7]

# ---------------------------------------------------------------------------
# 通用腿：16 宽，放在 x=8, y=28（第一行平时被衣摆盖住，抬身帧露出）
#   C/c = 裤子（cloth 角色），L/l = 靴子（leather）
# ---------------------------------------------------------------------------
LEGS_FRONT = {
    'stand': '''
        ....oCcooCco....
        ....oCcooCco....
        ...oLLlooLLlo...
        ...oooooooooo...
    ''',
    'pass': '''
        ....oCcooCco....
        ....oCcooCco....
        ...oLLlooLLlo...
        ...oooooooooo...
    ''',
    'stepA': '''
        ....oCcooCco....
        ....oCcooLLo....
        ...oLLlooooo....
        ...ooooo........
    ''',
    'stepB': '''
        ....oCcooCco....
        ....oLLooCco....
        ....oooooLLlo...
        ........ooooo...
    ''',
}

LEGS_SIDE = {
    'strideA': '''
        ......oCCco.....
        .....oCcooCco...
        ....oLLo..oLLo..
        ....ooo...ooo...
    ''',
    'strideB': '''
        ......oCCco.....
        .....oCcooCco...
        ....oLLo..oLLo..
        ....ooo...ooo...
    ''',
    'passA': '''
        ......oCCo......
        ......oCco......
        .....oLLlLo.....
        .....oooooo.....
    ''',
    'passB': '''
        ......oCCo......
        ......oCco......
        .....oLLlLo.....
        .....oooooo.....
    ''',
}


def recolor(d, mp):
    tr = str.maketrans(mp)
    if isinstance(d, str):
        return d.translate(tr)
    return {k: v.translate(tr) for k, v in d.items()}


def mirror(s):
    """水平镜像一段像素图（字符串或行列表）"""
    rows = art(s) if isinstance(s, str) else s
    w = max(len(r) for r in rows)
    return '\n'.join(r.ljust(w, '.')[::-1] for r in rows)


def pole(top, length, shaft='D', grips=(), grip='S', tail=()):
    """长柄武器：top 为枪头/杖头若干行，其下接 length 行柄（位于 top 的中心列）。
    grips: 柄的第几行换成手；tail: 柄下再追加的行（如枪尾）。"""
    rows = art(top) if isinstance(top, str) else list(top)
    w = len(rows[0])
    cx = w // 2
    for i in range(length):
        ch = grip if i in grips else shaft
        rows.append('.' * cx + ch + '.' * (w - cx - 1))
    for t in tail:
        rows.append('.' * cx + t + '.' * (w - cx - 1))
    return rows


LEGS_FRONT_T = recolor(LEGS_FRONT, {'C': '3', 'c': '2'})
LEGS_SIDE_T = recolor(LEGS_SIDE, {'C': '3', 'c': '2'})
LEGS_FRONT_D = recolor(LEGS_FRONT, {'C': 'y', 'c': 'x'})
LEGS_SIDE_D = recolor(LEGS_SIDE, {'C': 'y', 'c': 'x'})

# 重甲腿（knight / general）：3 宽腿甲（阵营色）+ 钢靴
LEGS_ARMOR_FRONT = {
    'stand': '''
        ...o332oo332o...
        ...o332oo332o...
        ..oWMMmooWMMmo..
        ..oooooooooooo..
    ''',
    'pass': '''
        ...o332oo332o...
        ...o332oo332o...
        ..oWMMmooWMMmo..
        ..oooooooooooo..
    ''',
    'stepA': '''
        ...o332oo332o...
        ...o332ooWMMmo..
        ..oWMMmoooooo...
        ..oooooo........
    ''',
    'stepB': '''
        ...o332oo332o...
        ..oWMMmoo332o...
        ...ooooooWMMmo..
        ........oooooo..
    ''',
}

LEGS_ARMOR_SIDE = {
    'strideA': '''
        .....o43322o....
        ....o332oo332o..
        ...oWMMo..oWMMo.
        ...oooo...oooo..
    ''',
    'strideB': '''
        .....o43322o....
        ....o332oo332o..
        ...oWMMo..oWMMo.
        ...oooo...oooo..
    ''',
    'passA': '''
        .....o43322o....
        ......o332o.....
        .....oWMMmo.....
        .....oooooo.....
    ''',
    'passB': '''
        .....o43322o....
        ......o332o.....
        .....oWMMmo.....
        .....oooooo.....
    ''',
}

# 长袍下摆（cleric / mage / civilian）：下摆随步伐摆动，脚尖露出
ROBE_FRONT = {
    'stand': '''
        ...o43333222o...
        ..o4333332222o..
        ..o4333322221o..
        ..oooooooooooo..
    ''',
    'pass': '''
        ...o43333222o...
        ..o4333332222o..
        ..o4333322221o..
        ..oooooooooooo..
    ''',
    'stepA': '''
        ...o43333222o...
        ..o4333332222o..
        .oL433322221o...
        .oooooooooooo...
    ''',
    'stepB': '''
        ...o43333222o...
        ..o4333332222o..
        ...o43333222Llo.
        ...oooooooooooo.
    ''',
}

ROBE_SIDE = {
    'strideA': '''
        .....o43322o....
        ....o4333222o...
        ...oL43332221o..
        ...ooooooooooo..
    ''',
    'strideB': '''
        .....o43322o....
        ....o4333222o...
        ....o433322221o.
        ....oooooLlooo..
    ''',
    'passA': '''
        .....o43322o....
        ....o4333222o...
        ....o43332221o..
        ....oooooooooo..
    ''',
    'passB': '''
        .....o43322o....
        ....o4333222o...
        ....o43332221o..
        ....oooooooooo..
    ''',
}


def foot_view(upper, split, legs, top=15, x=8, legs_y=28, before=(), after=(), torso=None, head=None, mid=()):
    """upper: 头+身合图（从 y=top 起）；split: 头部占的行数。
    torso / head: 可选 {变体键: 行列表} 覆盖对应段。before/after: 额外图层。"""
    rows = art(upper) if isinstance(upper, str) else upper
    head_rows = rows[:split]
    body_rows = rows[split:]
    layers = list(before)
    layers.append(Layer(legs, x, legs_y, 'legs'))
    tv = {'base': body_rows}
    if torso:
        tv.update({k: art(v) for k, v in torso.items()})
    layers.append(Layer(tv, x, top + split, 'body'))
    layers.extend(mid)
    hv = {'base': head_rows}
    if head:
        hv.update({k: art(v) for k, v in head.items()})
    layers.append(Layer(hv, x, top, 'head'))
    layers.extend(after)
    return layers


# ---------------------------------------------------------------------------
# 模型：lord
# ---------------------------------------------------------------------------
def model_lord():
    mats = dict(hair='hair_ash', eye='eye_blue', metal='steel', cloth='cloth_white')
    front = foot_view('''
        .....oooooo.....
        ...ooYYYHHHoo...
        ..oYYYHHHHHHHo..
        ..oYYHHHHHHHho..
        .oYHHHHHHHHHhho.
        .ohHSHHSHHShhho.
        ..ohSeSSSSeshho.
        ...oSeSSSSesso..
        ..o1ooSSSsoo1o..
        .o1oWMooooMmo1o.
        o21oMm4VV4mmo12o
        o21o32444322o12o
        o21oSoGGGGoSo12o
        o22o.o4332o.o22o
    ''', 9, LEGS_FRONT, torso={'idle2': '''
        .o1oWMooooMmo1o.
        o21oMm4VV4mmo12o
        o21o32444322o12o
        o21oSoGGGGoSo12o
        o221.o4332o.o122
    '''}, after=[
        Layer({'base': '''
            ..o.
            .oGo
            oGQG
            .oWo
            oWmo
            oWo.
            .o..
        ''', 'idle2': '''
            ..o.
            .oGo
            oGQG
            .oWo
            .Wmo
            oWo.
            oo..
        '''}, 9, 25, 'body'),
    ])
    back = foot_view('''
        .....oooooo.....
        ...ooYYYHHHoo...
        ..oYYYHHHHHHHo..
        ..oYYHHHHHHHho..
        .oYHHHHHHHHHhho.
        .ohHHHHHHHHhhho.
        .ohHHHHHHHhhhho.
        ..ohhHHHHhhhho..
        ..o1ohhhhhho1o..
        .o3oWM3332Mmo2o.
        o33oMm33322mo22o
        o33333332122222o
        oS333333212222So
        o22222221122222o
    ''', 9, LEGS_FRONT)
    side = foot_view('''
        ......oooooo....
        ....ooYYYHHHoo..
        ...oYYHHHHHHHho.
        ..oYHHHHHHHHHho.
        ..oYHHHHHHHhhho.
        ..oHSSHSHHhhhho.
        .oSSeSSSHhhhho..
        .oSSeSSShhhho...
        ..ooSSSsohho....
        ....oWMMo1o.....
        ...oWmmMo21o....
        ...o3SS3o221o...
        ...oGGGGo2221o..
        ....o332o22221o.
    ''', 9, LEGS_SIDE, after=[
        Layer('''
            ...oGo
            ..oWGo
            .oWo..
            oMo...
            .o....
        ''', 8, 25, 'body'),
    ])
    return dict(kind='foot', mats=mats, views=dict(front=front, back=back, side=side))


LANCE_HEAD = '''
    .W.
    WWm
    WMm
    .M.
    .m.
'''


def model_soldier():
    mats = dict(hair='hair_brown', eye='eye_brown', metal='steel', cloth='cloth_brown')
    lance_f = Layer(pole(LANCE_HEAD, 21, grips=(17,), tail='dd'), 10, 5, 'body')
    lance_b = Layer(pole(LANCE_HEAD, 21, grips=(17,), tail='dd'), 19, 5, 'body')
    lance_s = Layer(pole(LANCE_HEAD, 21, grips=(16,), tail='dd'), 11, 5, 'body')
    front = foot_view('''
        .....oooooo.....
        ...ooWWWMMMoo...
        ..oWWMMMMMMMmo..
        ..oWMMMMMMMMmo..
        .oWMMMMMMMMMmmo.
        .onmmmmmmmmmmno.
        ..oMSeSSSSesMo..
        ...oSeSSSSeso...
        ....ooSSSsoo....
        ..o43oooooo32o..
        ..o43LBLLLl32o..
        ..o32LLLLLl22o..
        ..oSsolllloSso..
        .....o3332o.....
    ''', 9, LEGS_FRONT, mid=[lance_f])
    back = foot_view('''
        .....oooooo.....
        ...ooWWWMMMoo...
        ..oWWMMMMMMMmo..
        ..oWMMMMMMMMmo..
        .oWMMMMMMMMMmmo.
        .onmmmmmmmmmmno.
        ..oMHHHHHHhhMo..
        ...ohHHHHhhho...
        ....oohhhhoo....
        ..o43oooooo32o..
        ..o43LLLLLl32o..
        ..o32LlLLLl22o..
        ..oSsolllloSso..
        .....o3332o.....
    ''', 9, LEGS_FRONT, mid=[lance_b])
    side = foot_view('''
        ......oooooo....
        ....ooWWWMMMoo..
        ...oWWMMMMMMMmo.
        ..oWMMMMMMMMMmo.
        ..oWMMMMMMMMMmo.
        ..onmmmmmmmmmno.
        .oSSeSSMMMmmo...
        .oSSeSSSMmmo....
        ..ooSSSsooo.....
        .....o433lo.....
        ....o4433llo....
        ....oSs33Llo....
        .....ollllo.....
        .....o3332o.....
    ''', 9, LEGS_SIDE, mid=[lance_s])
    return dict(kind='foot', mats=mats, views=dict(front=front, back=back, side=side))


BOW_R = '''
    ..T
    .Dw
    D.w
    D.w
    D.w
    D.w
    D.w
    D.w
    D.w
    .Dw
    ..T
'''
BOW_L = mirror(BOW_R)


def model_archer():
    mats = dict(hair='hair_brown', eye='eye_brown', metal='steel', cloth='cloth_brown')
    quiver_b = Layer('''
        ..VX.
        ..VV.
        ..LLl
        .LLl.
        .Ll..
        LLl..
        Ll...
    ''', 17, 20, 'body')
    quiver_s = Layer('''
        .VX
        .VV
        .LL
        LLl
        LLl
        Ll.
        l..
    ''', 18, 20, 'body')
    front = foot_view('''
        ......oooo......
        ....ooWWMMoo....
        ...oWWMMMMMmo...
        ..oWMMMMMMMMmo..
        oWWMMMMMMMMMMMmo
        .onnnnnnnnnnnno.
        ..ohSeSSSSeSho..
        ...oSeSSSSeso...
        ....ooSSSsoo....
        ..o43oooooo32o..
        ..o43l4433332o..
        ..o3234l33322o..
        ..oSsolllloSso..
        .....o3332o.....
    ''', 9, LEGS_FRONT, after=[Layer(BOW_R, 21, 21, 'body')])
    back = foot_view('''
        ......oooo......
        ....ooWWMMoo....
        ...oWWMMMMMmo...
        ..oWMMMMMMMMmo..
        oWWMMMMMMMMMMMmo
        .onnnnnnnnnnnno.
        ..ohHHHHHHhhho..
        ...ohHHHHhhho...
        ....oohhhhoo....
        ..o43oooooo32o..
        ..o4333333332o..
        ..o3233333322o..
        ..oSsolllloSso..
        .....o3332o.....
    ''', 9, LEGS_FRONT, before=[Layer(BOW_L, 8, 21, 'body')], after=[quiver_b])
    side = foot_view('''
        .......oooo.....
        .....ooWWMMoo...
        ....oWWMMMMMmo..
        ...oWMMMMMMMMmo.
        .oWWMMMMMMMMMMmo
        ..onnnnnnnnnnno.
        .oSSeSShhhho....
        .oSSeSSShho.....
        ..ooSSSsoo......
        .....o433o......
        ....o44333o.....
        ....oSs332o.....
        .....ollllo.....
        .....o3332o.....
    ''', 9, LEGS_SIDE, before=[quiver_s], after=[Layer('''
        ..T
        .Dw
        D.w
        D.w
        D.w
        D.w
        .Dw
        ..T
    ''', 10, 24, 'body')])
    return dict(kind='foot', mats=mats, views=dict(front=front, back=back, side=side))


AXE_HEAD_L = '''
    .W...D
    WWM.mD
    WMMmmD
    WMMmmD
    WMmmmD
    WWm.mD
    .W...D
'''


def model_fighter():
    mats = dict(hair='hair_blonde', eye='eye_brown', metal='steel', cloth='cloth_brown')
    axe_f = Layer(pole(AXE_HEAD_L, 0) + ['.....D'] * 9 + ['.....S', '.....d', '.....d'], 4, 11, 'body')
    axe_b = Layer(art(mirror(pole(AXE_HEAD_L, 0) + ['.....D'] * 9 + ['.....S', '.....d', '.....d'])), 21, 11, 'body')
    axe_s = Layer(pole(AXE_HEAD_L, 0) + ['.....D'] * 8 + ['.....S', '.....d', '.....d', '.....d'], 7, 11, 'body')
    front = foot_view('''
        .....oooooo.....
        ...ooHHHHHhoo...
        ..oHHHHHHHHhho..
        ..oHHHHHHHhhho..
        .o44444444443o3o
        .o22222222221o2o
        ..oSSeSSSSeSso..
        ...oSeSSSSeso...
        ....ooSSSsoo....
        ..oSSoooooosso..
        .oSS43SSSs32sso.
        .oSs34333222sso.
        .oSSoLLLLLLosso.
        ...o33332222o...
    ''', 9, LEGS_FRONT_T, mid=[axe_f])
    back = foot_view('''
        .....oooooo.....
        ...ooHHHHHhoo...
        ..oHHHHHHHHhho..
        ..oHHHHHHHhhho..
        .o444443344443o.
        .o222221122221o.
        ..ohHHH22HHhho..
        ...ohHH21hhho...
        ....oohhhhoo....
        ..oSSoooooosso..
        .oSS34333322sso.
        .oSs33333222sso.
        .oSSoLLLLLLosso.
        ...o33332222o...
    ''', 9, LEGS_FRONT_T, mid=[axe_b])
    side = foot_view('''
        ......oooooo....
        ....ooHHHHHhoo..
        ...oHHHHHHHHhho.
        ..oHHHHHHHHhhho.
        .o44444444444o3o
        .o2222222221o2o.
        .oSSeSSShhhho...
        .oSSeSSShhho....
        ..ooSSSsooo.....
        .....oSs33o.....
        ....oSSs333o....
        ....oSs3332o....
        ....oSoLLllo....
        .....o3332o.....
    ''', 9, LEGS_SIDE_T, mid=[axe_s])
    return dict(kind='foot', mats=mats, views=dict(front=front, back=back, side=side))


GREATSWORD_V = '''
    ..W..
    .WWm.
    .WMm.
    .WMm.
    .WMm.
    .WMm.
    .WMm.
    .WMm.
    .WMm.
    .WMm.
    .WMm.
    .WMm.
    .WMm.
    .WMm.
    GGQGg
    ..lSS
    ..G..
'''


def model_mercenary():
    mats = dict(hair='hair_brown', eye='eye_brown', metal='steel', cloth='cloth_brown')
    sword_f = Layer(GREATSWORD_V, 5, 11, 'body')
    sword_b = Layer(mirror(GREATSWORD_V), 22, 11, 'body')
    front = foot_view('''
        ....oo.oooo.....
        ...oYHoYHHHoo...
        ..oYHHHHHHHHho..
        .o444444444433o.
        .ohHHHHHHHHhhho.
        .ohSHHSHHShhhho.
        ..ohSeSSSSeShho.
        ...oSeSSSSesso..
        ....ooSSSsoo....
        ..o43oooooo32o..
        .o443LBLLl3322o.
        .o432LLLLl3221o.
        .o32SolllloS21o.
        ..oo.o3332o.oo..
    ''', 9, LEGS_FRONT, after=[sword_f])
    back = foot_view('''
        ....oo.oooo.....
        ...oYHoYHHHoo...
        ..oYHHHHHHHHho..
        .o444443344433o.
        .ohHHHH22HHhhho.
        .ohHHHH21HHhhho.
        .ohhHHHHHHhhhho.
        ..ohhHHHHhhhho..
        ...oohhhhhhoo...
        ..o4433333322o..
        .o443333333222o.
        .o433333332221o.
        .oS3333333222So.
        ..o2222222211o..
    ''', 9, LEGS_FRONT, after=[sword_b])
    side = foot_view('''
        .....oo.oooo....
        ....oYHoYHHHoo..
        ...oYHHHHHHHHho.
        ..o44444444443o3
        ..ohHHHHHHhhho3o
        ..oHSSHSHhhhho..
        .oSSeSSShhhhho..
        .oSSeSSShhhho...
        ..ooSSSsohho....
        .....o4332o.....
        ....o44L3221o...
        ....oS3LL3221o..
        ....oolllo3221o.
        .....o332oo21o..
    ''', 9, LEGS_SIDE, after=[Layer('''
        ....o..............
        ...oGoWWWWWWWWWWWW.
        .SSGGWMMMMMMMMMMMMm
        ...oGommmmmmmmmmmm.
        ....o..............
    ''', 9, 21, 'body')])
    return dict(kind='foot', mats=mats, views=dict(front=front, back=back, side=side))


def model_thief():
    mats = dict(hair='hair_red', eye='eye_amber', metal='steel', cloth='cloth_teal')
    tail_f = Layer({'base': '''
        .Cc.
        .cCc
        ..uc
        ...u
    ''', 'idle2': '''
        .Cc.
        .cC.
        .uc.
        ..u.
    ''', 'stepA': '''
        .Cc.
        .cCc
        ..ucu
        .....
    '''}, 17, 25, 'body')
    dagger_f = Layer({'base': '''
        .G.
        W..
        W..
    ''', 'idle2': '''
        .G.
        .W.
        W..
    '''}, 9, 28, 'body')
    front = foot_view('''
        ....o..oo..o....
        ...oHooHHooHo...
        ..oHHHHHHHHHHo..
        ..oYHHHHHHHHho..
        .oYHHHHHHHHHhho.
        .ohHSHhSHhSShho.
        ..ohSeSSSSeShho.
        ...oSeSSSSesso..
        ....ooSSSsoo....
        ...ooCCCCCcoo...
        ..o43CCCCcC32o..
        ..o324433uc22o..
        ..oSolLLlcoSo...
        ....o333322o....
    ''', 9, LEGS_FRONT_D, after=[tail_f, dagger_f])
    back = foot_view('''
        ....o..oo..o....
        ...oHooHHooHo...
        ..oHHHHHHHHHHo..
        ..oYHHHHHHHHho..
        .oYHHHHHHHHHhho.
        .ohHHHHHHHhhhho.
        .ohhHHHHHHhhhho.
        ..ohhHHHHhhho...
        ...ooCCCCCcoo...
        ..o43CCCCCc32o..
        ..o3244Cc3322o..
        ..oSo33uc322So..
        ....o333322o....
    ''', 8, LEGS_FRONT_D, top=16)
    side = foot_view('''
        .....o..oo.o....
        ....oHooHHoHo...
        ...oHHHHHHHHHo..
        ..oYHHHHHHHHhho.
        ..oHHHHHHHHhhhho
        ..oHSSHSHHhhhho.
        .oSSeSSSHhhhho..
        .oSSeSSShhhho...
        ..ooSSSsooo.....
        ....ooCCCCcoo...
        ....oCCCcuCcuo..
        ....oS3322o.uco.
        .....olLllo..u..
        .....o3322o.....
    ''', 9, LEGS_SIDE_D, after=[Layer('''
        .G
        W.
        W.
    ''', 11, 26, 'body')])
    return dict(kind='foot', mats=mats, views=dict(front=front, back=back, side=side))


def model_hunter():
    mats = dict(hair='hair_brown', eye='eye_green', metal='steel', cloth='cloth_brown')
    quiver_b = Layer('''
        .VX..
        .VV..
        .LLl.
        ..LLl
        ..LLl
        ...Ll
    ''', 17, 21, 'body')
    front = foot_view('''
        ......oooo......
        ....oo5443oo....
        ...o54444333o...
        ..o5443333332o..
        ..o4433333322o..
        ..o43hHHHHh21o..
        ..o3hSeSSeSh2o..
        ..o32SeSSes21o..
        ...o32sSSs21o...
        ..o433LLLL332o..
        .o4332LLLl2322o.
        .o332SLLLlS222o.
        .o3321lGGl1222o.
        .o3321oCCo1221o.
    ''', 9, LEGS_FRONT, after=[Layer(BOW_R, 21, 21, 'body')])
    back = foot_view('''
        ......oooo......
        ....oo5443oo....
        ...o54444333o...
        ..o5443333332o..
        ..o4433333322o..
        ..o4333333322o..
        ..o3333333222o..
        ..o3333332222o..
        ...o33332222o...
        ..o4333333322o..
        .o443333333222o.
        .o433333332221o.
        .oS3333333222So.
        .o332222222221o.
    ''', 9, LEGS_FRONT, after=[quiver_b])
    side = foot_view('''
        .......ooooo....
        .....oo54433o...
        ....o5444333oo..
        ...o5443333322o.
        ..o44333333222o.
        ..o43hHHH32222o.
        .oSSeSSh32222o..
        .oSSeSSSh3221o..
        ..ooSSSso3221o..
        ....oLLLo3321o..
        ...oLLLL33221o..
        ...oSLLl33221o..
        ....olll33221o..
        .....oCCo3321o..
    ''', 9, LEGS_SIDE, after=[Layer('''
        ..T
        .Dw
        D.w
        D.w
        D.w
        D.w
        .Dw
        ..T
    ''', 9, 24, 'body')])
    return dict(kind='foot', mats=mats, views=dict(front=front, back=back, side=side))


def model_usurper():
    # 瓦尔德：黑甲金边、暗色披风（阵营色压暗，敌方时即暗红）、灰丝黑发后梳、短尖胡、大剑拄地
    mats = dict(hair='hair_black', eye='eye_grey', metal='iron', dark='cloth_black', cloth='hair_grey')
    blade_f = Layer('''
        Wm
        Wm
        .m
    ''', 15, 29, 'body')
    collar = Layer('''
        1..........1
        21........12
        21........12
    ''', 10, 20, 'body')
    front = foot_view('''
        .....oooooo.....
        ...ooHHYYHHoo...
        ..oHHYCCHHHHho..
        ..oHCHHHHCChho..
        ..ohSSSSSSSShho.
        ..ohSSSSSSSShho.
        ..ohSeSSSSeShho.
        ...oSsShhSsSo...
        ....ohhHHhho....
        o1zWMzooooyMzy1o
        o2gGGgyQGygGGg2o
        o21yzySSSsyzx12o
        o21ygGQGGGGgx12o
        o22oyzoWmoyxo22o
    ''', 9, LEGS_FRONT_D, before=[collar], after=[blade_f])
    back = foot_view('''
        .....oooooo.....
        ...ooHHYYHHoo...
        ..oHHYCCHHHHho..
        ..oHCHHHHCChho..
        ..ohHHCCHHHhho..
        ..ohHHHHHCChho..
        ..ohhHHHHHhhho..
        ...ohhHHHhhho...
        ....oohhhhoo....
        o1zWMz2222yMzy1o
        o2gGGg3222gGGg2o
        o22333222222212o
        o22333222212222o
        o22233222212221o
    ''', 9, LEGS_FRONT_D, before=[collar], after=[Layer('''
        o2223322212221o
        .o12222212221o.
    ''', 9, 29, 'body')])
    side = foot_view('''
        ......oooooo....
        ....ooHHYYHHoo..
        ...oHHYCCHHHHho.
        ..oHCHHHHCChhho.
        ..ohHHHHHHhhhho.
        ..oSSSSHHHhhhho.
        .oSSeSSHHhhhho..
        .oSSsSSShhhho...
        ..oohhSsooo.....
        ....oMWz11o.....
        ...ogGGg2221o...
        ...oySSy22221o..
        ...oygGy222221o.
        ....oyzo2222221o
    ''', 9, LEGS_SIDE_D, before=[Layer('''
        ..12
        .122
        .122
    ''', 18, 20, 'body')], after=[Layer('''
        ..oGo
        .WW..
        WWm..
        Wm...
    ''', 7, 27, 'body')])
    return dict(kind='foot', mats=mats, views=dict(front=front, back=back, side=side))


STAFF_HEAD = '''
    .GQG.
    Gg.gG
    .GgG.
    ..G..
'''


def model_cleric():
    mats = dict(hair='hair_black', eye='eye_violet', white='cloth_white', gold='gold')
    staff_f = Layer(pole(STAFF_HEAD, 19, grips=(15,), tail='d'), 9, 7, 'body')
    staff_b = Layer(pole(STAFF_HEAD, 19, grips=(15,), tail='d'), 18, 7, 'body')
    staff_s = Layer(pole(STAFF_HEAD, 19, grips=(15,), tail='d'), 9, 7, 'body')
    front = foot_view('''
        .....oooooo.....
        ...ooXXXVVVoo...
        ..oXXVVVVVVVwo..
        ..oXVVVVVVVVwo..
        .oXVVVVVVVVVwwo.
        .oVVhHHHHHHhwwo.
        .oVwhSeSSeShwwo.
        .oVwhSeSSeshwwo.
        .oVwwosSSsowwwo.
        .oVwo43VV32owwo.
        .ow4433GG3322wo.
        ..oS43333322So..
        ..o4433333222o..
        ...o43333222o...
    ''', 9, ROBE_FRONT, mid=[staff_f])
    back = foot_view('''
        .....oooooo.....
        ...ooXXXVVVoo...
        ..oXXVVVVVVVwo..
        ..oXVVVVVVVVwo..
        .oXVVVVVVVVVwwo.
        .oXVVVVVVVVVwwo.
        .oVVVVVVVVVwwwo.
        .oVVVVVVVVwwwwo.
        .oVVVVVVVwwwwwo.
        .oVVVVVVwwwwwwo.
        .owVVVVwwwwwwwo.
        ..oS43333322So..
        ..o4433333222o..
        ...o43333222o...
    ''', 9, ROBE_FRONT, mid=[staff_b])
    side = foot_view('''
        ......oooooo....
        ....ooXXXVVVoo..
        ...oXXVVVVVVVwo.
        ..oXVVVVVVVVVwo.
        ..oXVVVVVVVVwwo.
        ..oVhHHHVVVwwwo.
        .oSSeShhVVwwwwo.
        .oSSeSShVwwwwwo.
        ..ooSSsoVwwwwo..
        ....o43oVwwwo...
        ...o443GoVwwo...
        ...oS4333oVwo...
        ....o43332oo....
        ....o433322o....
    ''', 9, ROBE_SIDE, mid=[staff_s])
    return dict(kind='foot', mats=mats, views=dict(front=front, back=back, side=side))


def model_mage():
    mats = dict(hair='hair_lav', eye='eye_gold', gold='gold', leather='leather', dark='cloth_crimson')
    front = foot_view('''
        .....oooooo.....
        ...ooYYHHHHoo...
        ..oYYHHHHHHHho..
        ..oYHHHHHHHHho..
        .oYHHHHHHHHHhho.
        .oHHHHHHHHHHhho.
        .oHhSeSSSSeShho.
        .oHhSeSSSSeshho.
        .oHhhoSSSsohhho.
        .ohho4oooo3ohho.
        ..o43zzGyyx32o..
        ..oSSyyGyyxSSo..
        ..o43XXXXVV32o..
        ...o43333222o...
    ''', 9, ROBE_FRONT)
    back = foot_view('''
        .....oooooo.....
        ...ooYYHHHHoo...
        ..oYYHHHHHHHho..
        ..oYHHHHHHHHho..
        .oYHHHHHHHHHhho.
        .oHHHHHHHHHhhho.
        .oHHHHHHHHhhhho.
        .ohHHHHHHhhhhho.
        .ohhhHHHhhhhhho.
        .ohhoGGGGGGohho.
        ..o4433333322o..
        ..oS43333322So..
        ..o4333333222o..
        ...o43333222o...
    ''', 9, ROBE_FRONT)
    side = foot_view('''
        ......oooooo....
        ....ooYYHHHHoo..
        ...oYYHHHHHHHho.
        ..oYHHHHHHHHHho.
        ..oHHHHHHHHhhho.
        ..oHHHHHHHhhhho.
        .oSSeSShHhhhho..
        .oSSeSShhhhho...
        ..ooSSsohhho....
        ....oG43hho.....
        ...ozzyy3322o...
        ...oSyGx33322o..
        ...ooXVVx3322o..
        ....o4333222o...
    ''', 9, ROBE_SIDE)
    return dict(kind='foot', mats=mats, views=dict(front=front, back=back, side=side))


def model_civilian():
    # 村长玛莎：头巾、白发、拄杖，略驼背（整体矮 1px）
    mats = dict(skin='skin_old', hair='hair_grey', eye='eye_brown', cloth='cloth_brown', wood='wood')
    cane_f = Layer(['.DT', 'D.T', '.SD', '.TD', '.TD', '.Dd', '.Dd', '.dd'], 8, 23, 'body')
    cane_b = Layer(['TD.', 'T.D', 'DS.', 'DT.', 'DT.', 'dD.', 'dD.', 'dd.'], 21, 23, 'body')
    cane_s = Layer(['DT.', 'T.D', 'SD.', 'TD.', 'TD.', 'Dd.', 'Dd.', 'dd.'], 8, 23, 'body')
    front = foot_view('''
        .....oooooo.....
        ...ooUUCCCCoo...
        ..oUUCCCCCCCco..
        ..oUCCCCCCCCco..
        .oUCCHHHHHHCcco.
        .oCcHkSSSSkHcco.
        .oCcSSSssSSScco.
        ..oCcoSSSSocco..
        ..o43oooooo32o..
        .o44333CC33322o.
        .o4S33333333S2o.
        ..o4333333222o..
        ...o43333222o...
    ''', 8, ROBE_FRONT, top=16, mid=[cane_f])
    back = foot_view('''
        .....oooooo.....
        ...ooUUCCCCoo...
        ..oUUCCCCCCCco..
        ..oUCCCCCCCCco..
        .oUCCCCCCCCCcco.
        .oCCCCCCCCCccco.
        .oCcCCCCCCcccco.
        ..oCcccCCcccco..
        ..o43oCccCo32o..
        .o443333333322o.
        .o4S33333333S2o.
        ..o4333333222o..
        ...o43333222o...
    ''', 8, ROBE_FRONT, top=16, mid=[cane_b])
    side = foot_view('''
        ......oooooo....
        ....ooUUCCCCoo..
        ...oUUCCCCCCCco.
        ..oUCCCCCCCCcco.
        ..oCHHHCCCCccco.
        .oSkSSHCCCcccco.
        .oSSSSSCCcccco..
        ..ooSSoCCccco...
        ....o43occco....
        ...o44333322o...
        ...oS43333222o..
        ....o43333222o..
        ....o4333222o...
    ''', 8, ROBE_SIDE, top=16, mid=[cane_s])
    return dict(kind='foot', mats=mats, views=dict(front=front, back=back, side=side))


SHIELD_F = '''
    ooooooo
    oWWMMmo
    oM443mo
    oM4G3mo
    oMGQG2o
    oM3G2mo
    .oM22mo
    ..oM2o.
    ...oo..
'''


def model_knight():
    mats = dict(eye='eye_brown', metal='steel', gold='gold')
    lance_f = Layer(pole(LANCE_HEAD, 21, grips=(17,), grip='M', tail='dd'), 10, 5, 'body')
    lance_b = Layer(pole(LANCE_HEAD, 21, grips=(17,), grip='M', tail='dd'), 19, 5, 'body')
    lance_s = Layer(pole(LANCE_HEAD, 21, grips=(16,), grip='M', tail='dd'), 17, 5, 'body')
    front = foot_view('''
        .....oooooo.....
        ...oo444332oo...
        ..o5444433332o..
        ..o4444333332o..
        .oWMMMMMMMMmmmo.
        .oOOOOOOOOOOOOo.
        .o433333332222o.
        ..o3333332222o..
        ...o33322221o...
        o5443o3332o3322o
        o4332oWMMmo2221o
        .o332o3Mm3o221o.
        .oMMmoGGGGomMmo.
        ..o4333332222o..
    ''', 9, LEGS_ARMOR_FRONT, mid=[lance_f], after=[Layer(SHIELD_F, 19, 24, 'body')])
    back = foot_view('''
        .....oooooo.....
        ...oo444332oo...
        ..o5444433332o..
        ..o4444333332o..
        .oWMMMMMMMMmmmo.
        .o433333333222o.
        .o433333332222o.
        ..o3333332222o..
        ...o33322221o...
        o5443o3332o3322o
        o4332o3332o2221o
        .o332o3332o221o.
        .oMMmoGGGGomMmo.
        ..o4333332222o..
    ''', 9, LEGS_ARMOR_FRONT, mid=[lance_b], after=[Layer('''
        ooooooo
        oMMMMmo
        oM332mo
        oM322mo
        oM322mo
        oM322mo
        omM22mo
        .omM2o.
        ..ooo..
    ''', 6, 24, 'body')])
    side = foot_view('''
        ......oooooo....
        ....oo444332oo..
        ...o5444433332o.
        ..o54444333332o.
        ..oWMMMMMMMmmmo.
        .oOOOOO3333222o.
        .o43333333222o..
        ..o333333222o...
        ...o3332222o....
        ...o5443332o....
        ..o44333322o....
        ..o433Mm322o....
        ..oMMmGGGgmo....
        ...o4333222o....
    ''', 9, LEGS_ARMOR_SIDE, mid=[lance_s], after=[Layer('''
        ooooo.
        oWWMmo
        oM43mo
        oMG3mo
        oM32mo
        oM32mo
        oMm2mo
        .oMmo.
        ..oo..
    ''', 8, 23, 'body')])
    return dict(kind='foot', mats=mats, views=dict(front=front, back=back, side=side))


AXE2_HEAD = '''
    .W.D.W.
    WWmDmWW
    WMmDmMW
    WMmDmMW
    WWmDmWW
    .W.D.W.
'''
HORN_L = '''
    X....
    XV...
    .VV..
    .wV..
    ..wV.
    ...wV
    ....w
'''


def model_general():
    mats = dict(eye='eye_red', metal='steel', gold='gold')
    axe_f = Layer(pole(AXE2_HEAD, 16, grips=(13,), grip='M', tail='dd'), 6, 8, 'body')
    axe_b = Layer(pole(AXE2_HEAD, 16, grips=(13,), grip='M', tail='dd'), 19, 8, 'body')
    axe_s = Layer(pole(AXE2_HEAD, 16, grips=(12,), grip='M', tail='dd'), 16, 8, 'body')
    horns_f = [Layer(HORN_L, 5, 12, 'head'), Layer(mirror(HORN_L), 22, 12, 'head')]
    front = foot_view('''
        .....oooooo.....
        ...oo444332oo...
        ..o5444433332o..
        ..o4444333332o..
        .oGQGGGGGGGggqo.
        .o33OO33OOO22o..
        .o44333OO32222o.
        ..o3333O32222o..
        ...o33322221o...
        o54433oooo33322o
        o44332WMMmW3221o
        o4332oGQGGo2221o
        oMMMmo3332omMMmo
        ..o4333333222o..
    ''', 9, LEGS_ARMOR_FRONT, mid=[axe_f], after=horns_f)
    back = foot_view('''
        .....oooooo.....
        ...oo444332oo...
        ..o5444433332o..
        ..o4444333332o..
        .oGQGGGGGGGggqo.
        .o443333333222o.
        .o433333332222o.
        ..o3333332222o..
        ...o33322221o...
        o54433oooo33322o
        o44332333223221o
        o43322333222221o
        oMMMmo3332omMMmo
        ..o4333333222o..
    ''', 9, LEGS_ARMOR_FRONT, mid=[axe_b], after=horns_f)
    side = foot_view('''
        ......oooooo....
        ....oo444332oo..
        ...o5444433332o.
        ..o54444333332o.
        ..oGQGGGGGGggqo.
        .oOO3O33333222o.
        .o4OO333333222o.
        ..o333333222o...
        ...o3332222o....
        ...o54433322o...
        ..o443333222o...
        ..o4332Mm3221o..
        ..oMMMmGGGgmmo..
        ...o43333222o...
    ''', 9, LEGS_ARMOR_SIDE, mid=[axe_s], after=[Layer(HORN_L, 6, 12, 'head'), Layer(mirror(HORN_L), 20, 12, 'head')])
    return dict(kind='foot', mats=mats, views=dict(front=front, back=back, side=side))


# ---------------------------------------------------------------------------
# 马（侧面朝左）：共用给 cavalier；pegasus 换白色 + 翅膀
# ---------------------------------------------------------------------------
HORSE_SIDE_LEGS = {
    'stand': """
        AA.aa....AA.aa
        Aa.ap....Aa.ap
        Aa.ap....Aa.ap
        Aa.ap....Aa.ap
        Aa.ap....Aa.ap
        ff.ff....ff.ff
    """,
    'w0': """
        AA.aa....AA.aa
        Aa.ap....Aa.ap
        Aa..ap...Aa.ap
        Aa..ap....Aaap
        Aa...ap...Aaap
        ff...ff...ff.ff
    """,
    'w1': """
        AA.aa....AA.aa
        Aa.ap....Aa.ap
        .AaAp....Aa.ap
        ..ffap...Aa.ap
        ....ap...Aa.ap
        ....ff...ff.ff
    """,
    'w2': """
        AA.aa....AA.aa
        Aaaap...Aa..ap
        .Aa.ap..Aa..ap
        .Aa.ap.Aa...ap
        ..Aa.apAa...ap
        ..ff.ffff...ff
    """,
    'w3': """
        AA.aa....AA.aa
        Aa.ap....Aa.ap
        Aa.aap...Aa.ap
        Aa..ff...Aaap.
        Aa.......Aa...
        ff.......ff...
    """,
}

HORSE_SIDE_HEAD = """
    .......f.f.......
    ......fAfAf......
    .....fAAAAAf.....
    ....AAAeAAAAf....
    ...AAAAAAAAAf....
    ..AAAAAAAAAAAf...
    .PAAAApAAAAAAf...
    PAAAp..pAAAAAAf..
    PAAp....pAAAAAAf.
    .pp......pAAAAAAA
    ..........pAAAAAA
"""

HORSE_SIDE_BODY = """
    ......P433332P..
    .AAAAA4333322AAA
    ..AAAA4333322AAA
    ..AAAA2222221AAA
    ..aAAAAAAAAAAAAa
    ..aaAAAAAAAAAAaa
    ...aaaaaaaaaaaa.
"""

HORSE_TAIL = {
    'base': """
        f..
        Ff.
        fFf
        .fF
        .fF
        ..f
    """,
    'swish': """
        f...
        Ff..
        fFf.
        .fFf
        ..fF
        ...f
    """,
}


def horse_side(x0=0, y0=0):
    """侧面马的四个图层（尾、腿、身、头颈），整体偏移 x0,y0"""
    return dict(
        tail=Layer(HORSE_TAIL, 26 + x0, 20 + y0, 'mbody'),
        legs=Layer(HORSE_SIDE_LEGS, 12 + x0, 25 + y0, 'legs'),
        body=Layer(HORSE_SIDE_BODY, 10 + x0, 19 + y0, 'mbody'),
        head=Layer(HORSE_SIDE_HEAD, 2 + x0, 11 + y0, 'mhead'),
    )


RIDER_SIDE_BODY = """
    ...433..
    ..443322
    ..4S3322
    ...GGGg.
    ..44332.
    .443322.
    .LL3....
    .LLl....
    .LLl....
"""

# ---- 马（正面，朝镜头） ----
HORSE_FRONT_HEAD = """
    f......f
    Af....fA
    AAffffAA
    AAAffAAA
    AeAAAAeA
    AAAAAAAa
    .AAPAAa.
    .AAPAAa.
    .AAAAAa.
    .aPaaPa.
    ..aaaa..
"""
HORSE_FRONT_BODY = """
    ...AAAAAA...
    ..AAAAAAAA..
    3AAAAAAAAAA2
    32AAAAAAAaa1
    3AAAAAAAAAa2
    2aAAAAAAAAa1
    .aAAAAAAAAa.
    ..aaaaaaaa..
"""
HORSE_FRONT_LEGS = {
    'base': """
        AA.p..p.AA
        Aa.p..p.Aa
        Aa.p..p.Aa
        Aa.f..f.Aa
        Aa......Aa
        ff......ff
    """,
    'w0': """
        AA.p..p.AA
        Aa.p..p.Aa
        Aa.p..p.Aa
        Aa.f..f.ff
        Aa........
        ff........
    """,
    'w2': """
        AA.p..p.AA
        Aa.p..p.Aa
        Aa.p..p.Aa
        ff.f..f.Aa
        ........Aa
        ........ff
    """,
}
# ---- 马（背面，屁股朝镜头） ----
HORSE_BACK_BODY = """
    ...aAAAAa...
    ..aAAPPAAa..
    3aAAAffAAAa2
    3AAAAffAAAa1
    3AAAfFFfAAa2
    2aAAfFFfAaa1
    .aAAfFFfAaa.
    ..aafFFfaa..
    ....fFFf....
    ....fFFf....
    .....ff.....
"""
HORSE_BACK_LEGS = {
    'base': """
        AA......AA
        Aa......Aa
        Aa......Aa
        Aa......Aa
        Aa......Aa
        ff......ff
    """,
    'w0': """
        AA......AA
        Aa......Aa
        Aa......Aa
        Aa......ff
        Aa........
        ff........
    """,
    'w2': """
        AA......AA
        Aa......Aa
        Aa......Aa
        ff......Aa
        ........Aa
        ........ff
    """,
}


def horse_front(x0=0, y0=0):
    return dict(
        legs=Layer(HORSE_FRONT_LEGS, 11 + x0, 25 + y0, 'legs'),
        body=Layer(HORSE_FRONT_BODY, 10 + x0, 18 + y0, 'mbody'),
        head=Layer(HORSE_FRONT_HEAD, 12 + x0, 13 + y0, 'mhead'),
    )


def horse_back(x0=0, y0=0):
    return dict(
        legs=Layer(HORSE_BACK_LEGS, 11 + x0, 25 + y0, 'legs'),
        body=Layer(HORSE_BACK_BODY, 10 + x0, 17 + y0, 'mbody'),
    )


RIDER_FRONT_BODY = """
    ..o43oooooo32o..
    .o4433MWWM3322o.
    .o433MMMMm3221o.
    .oS33MmmMm322So.
    ..o33GGGGg322o..
    ..o3322222221o..
    .33..........32.
    .32..........22.
    .LL..........Ll.
    .LL..........Ll.
    .Ll..........ll.
"""
RIDER_BACK_BODY = """
    ..o43oooooo32o..
    .o443333333322o.
    .o433333332221o.
    .oS33333322221So
    ..o3333332222o..
    ..o3322222221o..
    .33..........32.
    .32..........22.
    .LL..........Ll.
    .LL..........Ll.
    .Ll..........ll.
"""
SHIELD_SMALL = """
    WWMm
    M43m
    MG3m
    M32m
    M32m
    .Mm.
"""


def model_cavalier():
    # 骑士（格伦）：灰发灰须、钢甲+阵营色披挂、栗色马、长枪+盾
    mats = dict(hair='hair_grey', eye='eye_grey', metal='steel', mount='leather', mane='hair_brown')
    h = horse_side()
    side = [
        h['tail'], h['legs'], h['body'],
        Layer(pole(LANCE_HEAD, 14, grips=(10,), tail='d'), 21, 2, 'rider'),
        h['head'],
        Layer(RIDER_SIDE_BODY, 15, 13, 'rider', outline=True),
        Layer(SHIELD_SMALL, 13, 13, 'rider', outline=True),
        Layer("""
            ......oooooo....
            ....ooYYYHHHoo..
            ...oYYHHHHHHHho.
            ..oYHHHHHHHHHho.
            ..oHHHHHHHHhhho.
            ..oHSSHSHHhhhho.
            .oSSeSSSHhhhho..
            .oSShhhShhhho...
            ..oohhhhohho....
        """, 11, 4, 'rhead'),
    ]
    hf = horse_front()
    head_f = Layer("""
        .....oooooo.....
        ...ooYYYHHHoo...
        ..oYYYHHHHHHHo..
        ..oYYHHHHHHHho..
        ..oYHHHHHHHHho..
        ..ohSSSSSSSSho..
        ..ohSeSSSSeSho..
        ...ohhSSSShho...
        ....ohhhhhho....
    """, 8, 2, 'rhead')
    front = [
        hf['legs'], hf['body'],
        Layer(RIDER_FRONT_BODY, 8, 11, 'rider', outline=True),
        Layer(pole(LANCE_HEAD, 18, grips=(8,), tail='d'), 8, 2, 'rider'),
        hf['head'],
        Layer(SHIELD_SMALL, 21, 12, 'rider', outline=True),
        head_f,
    ]
    hb = horse_back()
    head_b = Layer("""
        .....oooooo.....
        ...ooYYYHHHoo...
        ..oYYYHHHHHHHo..
        ..oYYHHHHHHHho..
        ..oYHHHHHHHHho..
        ..ohHHHHHHHhho..
        ..ohhHHHHHhhho..
        ...ohhhHHhhho...
        ....oohhhhoo....
    """, 8, 2, 'rhead')
    back = [
        hb['legs'],
        Layer(pole(LANCE_HEAD, 18, grips=(8,), tail='d'), 21, 2, 'rider'),
        Layer(RIDER_BACK_BODY, 8, 11, 'rider', outline=True),
        hb['body'],
        Layer(mirror(SHIELD_SMALL), 7, 12, 'rider', outline=True),
        head_b,
    ]
    return dict(kind='mount', mats=mats, views=dict(front=front, back=back, side=side))


# ---------------------------------------------------------------------------
# 天马（薇拉）：白马 + 浅蓝鬃 + 羽翼三态；飞行时收腿、整体上浮 2px
# ---------------------------------------------------------------------------
PEG_WING_SIDE = {
    'wup': """
        ..........XX.
        .........XVVw
        ........XVVwv
        .......XVVwv.
        ......XVVwwv.
        .....XVVwwv..
        ....XVVVwwv..
        ...XVVVwwv.v.
        ..XVVVwwv.v..
        .XVVVwwv.v...
        XVVVwwv......
        XVVwwv.v.....
        VVwwv........
        Vwwv.........
    """,
    'wmid': """
        ...........XXV
        .......XXXXVVw
        ....XXXVVVVwwv
        ..XXVVVVVwwwv.
        XXVVVVVwwwvv..
        XVVVVwwwv.v...
        VVVwwv.v......
        Vwwv.v........
    """,
    'wdown': """
        XXVv.........
        XVVVwv.......
        VVVVVwv......
        .VVVVVwwv....
        ..VVVVVwwv...
        ...wVVVVwwv..
        ....wVVVVwv..
        .....vwVVVwv.
        ......vwVVwv.
        .......vwVVw.
        ........vwVw.
        .........vwv.
    """,
}
PEG_WING_SIDE_POS = {'wup': (18, 5), 'wmid': (17, 11), 'wdown': (17, 16)}

PEG_WING_FRONT_L = {
    'wup': """
        X........
        XV.......
        XVw......
        XVVw.....
        XVVVw....
        XVVVVw...
        .XVVVVw..
        .XVVVVVw.
        .vXVVVVwv
        ..vXVVVVw
        ...vXVVVw
        ....vXVVw
        .....vXVw
        ......vww
    """,
    'wmid': """
        .XXXX.....
        XVVVVXXX..
        XVVVVVVVXX
        vwVVVVVVVw
        .vwwVVVVVw
        ..vv.wwVVw
        .....vvwww
    """,
    'wdown': """
        ......XXXw
        .....XVVVw
        ....XVVVwv
        ...XVVVwv.
        ..XVVVwv..
        .XVVVwv...
        XVVVwv....
        XVVwv.....
        VVwv......
        Vwv.......
    """,
}
PEG_WING_FRONT_POS = {'wup': (2, 4), 'wmid': (1, 12), 'wdown': (1, 15)}


def _wing_layers(arts, pos, tag='mbody', mirror_x=None):
    """把 {状态: 图} 拆成若干层（每个状态一层、只在该状态出现）"""
    out = []
    for k, a in arts.items():
        x, y = pos[k]
        if mirror_x is not None:
            rows = art(a)
            w = max(len(r) for r in rows)
            a = mirror(a)
            x = mirror_x - x - w + 1
        out.append(Layer({k: a, 'base': ['.']}, x, y, tag))
    return out


def _peg(a):
    """马的部件改成天马配色：鬃毛/尾巴变浅，蹄子用灰白"""
    return recolor(a, {'F': 'r', 'f': 'F'})


PEG_SIDE_LEGS = {'base': """
    AA.aa....AA.aa
    .Aaap....Aa.ap
    ..ppap....Aaap
    ....pp.....pp.
"""}
PEG_FRONT_LEGS = {'base': """
    AA.a..a.AA
    Aa.a..a.Aa
    Aa.p..p.Aa
    pp......pp
"""}


def model_pegasus():
    # 薇拉：银白长马尾、冰蓝眼、白+阵营色轻甲、翼形发饰；白色天马、浅蓝鬃毛；枪
    mats = dict(hair='hair_silver', eye='eye_ice', metal='steel', mount='cloth_white', mane='cloth_sky',
                white='cloth_white')
    y0 = -1
    side = [
        Layer(_peg(HORSE_TAIL), 26, 20 + y0, 'mbody'),
        Layer(PEG_SIDE_LEGS, 12, 25 + y0, 'mbody'),
        Layer(_peg(HORSE_SIDE_BODY), 10, 19 + y0, 'mbody'),
    ]
    side += _wing_layers(PEG_WING_SIDE, {k: (x, y + y0) for k, (x, y) in PEG_WING_SIDE_POS.items()})
    side += [
        Layer(pole(LANCE_HEAD, 11, grips=(7,), tail='d'), 21, 4, 'rider'),
        Layer(_peg(HORSE_SIDE_HEAD), 2, 11 + y0, 'mhead'),
        Layer("""
            ...433..
            ..44V322
            ..4S3322
            ...GGGg.
            ..44332.
            .443322.
            .VV3....
            .VVw....
            .VVw....
        """, 15, 13 + y0, 'rider', outline=True),
        Layer("""
            ......oooooo....
            ....ooYYYHHHoo..
            ...oYYHHHHHHHhoo
            ..oYHHHHHHHHHhYo
            ..oHHHHHHHXVhhHho
            ..oHSSHSHHhhhhhHo
            .oSSeSSSHhhhoohho
            .oSSeSSShhho..oho
            ..ooSSSsohho...o.
        """, 11, 4 + y0, 'rhead'),
    ]
    head_f = Layer("""
        .....oooooo.....
        ...ooYYYHHHoo...
        ..oYYYHHHHHHHo..
        .ooYYHHHHHHHhoo.
        oXoYHHHHHHHHhoXo
        oVohHSHHSHHShoVo
        .o.hSeSSSSeShho.
        ...oSeSSSSesso..
        ....ooSSSsoo....
    """, 8, 2 + y0, 'rhead')
    head_b = Layer("""
        .....oooooo.....
        ...ooYYYHHHoo...
        ..oYYYHHHHHHHo..
        .ooYYHHHHHHHhoo.
        oXoYHHHHHHHHhoXo
        oVohHHHHHHHhhoVo
        .o.ohhHHHHhho.o.
        ....ohhHHhho....
        .....ohHHho.....
        .....ohHHho.....
        ......ohho......
    """, 8, 2 + y0, 'rhead')
    body_f = recolor(RIDER_FRONT_BODY, {'L': 'V', 'l': 'w', 'W': 'X', 'M': 'V', 'm': 'w'})
    hf = dict(legs=Layer(PEG_FRONT_LEGS, 11, 25 + y0, 'mbody'),
              body=Layer(_peg(HORSE_FRONT_BODY), 10, 18 + y0, 'mbody'),
              head=Layer(_peg(HORSE_FRONT_HEAD), 12, 13 + y0, 'mhead'))
    wl = {k: (x, y + y0) for k, (x, y) in PEG_WING_FRONT_POS.items()}
    wings_f = _wing_layers(PEG_WING_FRONT_L, wl) + _wing_layers(PEG_WING_FRONT_L, wl, mirror_x=31)
    front = wings_f + [
        hf['legs'], hf['body'],
        Layer(body_f, 8, 11 + y0, 'rider', outline=True),
        Layer(pole(LANCE_HEAD, 14, grips=(5,), tail='d'), 8, 4, 'rider'),
        hf['head'],
        head_f,
    ]
    hb = dict(legs=Layer(PEG_FRONT_LEGS, 11, 25 + y0, 'mbody'),
              body=Layer(_peg(HORSE_BACK_BODY), 10, 17 + y0, 'mbody'))
    back = wings_f + [
        hb['legs'],
        Layer(pole(LANCE_HEAD, 14, grips=(5,), tail='d'), 21, 4, 'rider'),
        Layer(recolor(RIDER_BACK_BODY, {'L': 'V', 'l': 'w'}), 8, 11 + y0, 'rider', outline=True),
        hb['body'],
        head_b,
    ]
    return dict(kind='fly', mats=mats, views=dict(front=front, back=back, side=side))


# ---------------------------------------------------------------------------
# 飞龙（wyvern）：深绿鳞身、土黄腹与角、橄榄色翼膜；骑手戴盔持枪
#   A/a/P/p = 鳞（mount）；F/f/r/R = 腹/角（mane）；C/c/U/u = 翼膜（cloth）
# ---------------------------------------------------------------------------
WYV_SIDE_HEAD = """
    .......RR......
    .....AAARr.....
    ...AAAPAAAr....
    .AAAAAQAAAA....
    AAPPAAAAAAAA...
    AAAAAaaAAAAAA..
    .aFFFa.aAAAAA..
    ..aaa...aAAAAA.
    .........aAAAA.
    ..........AAAAA
    ..........aAAAA
    ...........AAAA
"""
WYV_SIDE_BODY = """
    .....PPPPPP....
    ...AAAA4332AAA.
    ..AAAAA4332AAAA
    .AAAAAA2221AAAA
    AAAAAAAAAAAAAAA
    FFrrrrAAAAAAAAa
    .FFFFrrAAAAAAaa
    ..FFFFFaaaaaaa.
    ....aaaa.......
"""
WYV_SIDE_TAIL = {'base': """
    AA.....
    AAAA...
    aAAAA..
    .aaAAA.
    ...aaAA
    .....aA
    ......a
""", 'wdown': """
    AA.....
    AAAA...
    aAAAA..
    .aaAAAA
    ...aaaA
    ......a
"""}
WYV_SIDE_LEGS = """
    .AAAa.aa.
    AAAAa.aa.
    .aAAa.ap.
    .aAa..ap.
    RfRf..fr.
"""
WYV_WING_SIDE = {
    'wup': """
        .............Aa
        ...........AAAC
        .........AAACCc
        .......AAACCCc.
        ......AACCCCc..
        .....AACCACCc..
        ....AACCCACCc..
        ...AACCCACCcc..
        ...ACCCCACCc.c.
        ..AACCCACCc....
        ..ACCCCACc.c...
        .AACCCACc......
        .ACCCCAc.c.....
        AACCCAc........
        ACCCAc.........
        ACCc.c.........
    """,
    'wmid': """
        ..........AAAAA
        ......AAAAACCCC
        ...AAACCCCCCCCc
        .AAACCCCACCCCc.
        AACCCCACCCCc.c.
        ACCCCACCCc.c...
        ACCCACCCc......
        ACCACCc.c......
        ACCc.c.........
    """,
    'wdown': """
        AAAC..........
        ACCCAc........
        .ACCCCAc......
        .ACCCCCCAc....
        ..ACCCCCCCAc..
        ..ACCCCCCCCCc.
        ...ACCCCCCCc..
        ...ACCCCCCc...
        ....ACCCCc....
        ....ACCc......
        .....Ac.......
    """,
}
WYV_WING_SIDE_POS = {'wup': (16, 2), 'wmid': (16, 9), 'wdown': (16, 16)}

WYV_FRONT_HEAD = """
    R......R
    rA....Ar
    .AAAAAA.
    AQAAAAQA
    AAAAAAAA
    .aAFFAa.
    ..aFFa..
"""
WYV_FRONT_BODY = """
    ...AAAAAA...
    ..AAAAAAAA..
    3AAAFFFFAAA2
    3AAFFrrFFAA1
    2AAFrrrrFAa1
    .aAFFrrFFAa.
    ..aaFFFFaa..
"""
WYV_BACK_BODY = """
    ...AAAAAA...
    ..AAAAPAAA..
    3AAAAAAAAAA2
    3AAAAAAAAAa1
    2aAAAAAAAAa1
    .aaAAAAAAaa.
    ...aAAAAa...
    ....aAAa....
    ....aAAa....
    .....aa.....
"""
WYV_FRONT_LEGS = """
    .AAa....aAA.
    .aAa....aAa.
    .RfR....RfR.
"""
WYV_WING_FRONT_L = {
    'wup': """
        A.........
        AA........
        ACA.......
        ACCA......
        ACCCA.....
        ACCACA....
        ACCACCA...
        ACACCCCA..
        .cACCCCCA.
        ..cACCCCCA
        ...cCACCCA
        ....cCACCA
        .....cCCCA
        ......cCCA
        .......ccA
    """,
    'wmid': """
        AAAA.......
        ACCCAAAA...
        .cCCCCCCAAA
        ..cACCCCCCA
        ...cACCCCCA
        ....cACCCCA
        .....ccCCCA
        .......ccCA
    """,
    'wdown': """
        .......AAAA
        .....AACCCA
        ...AACCCCCA
        .AACCACCCCA
        AACCACCCCA.
        ACCACCCCc..
        ACACCCc....
        .ACCc......
        .Ac........
    """,
}
WYV_WING_FRONT_POS = {'wup': (1, 3), 'wmid': (1, 12), 'wdown': (1, 14)}


def model_wyvern():
    mats = dict(hair='hair_brown', eye='eye_brown', metal='steel', mount='forest', mane='earth',
                cloth='stone')
    side = [
        Layer(WYV_SIDE_TAIL, 24, 19, 'mbody'),
        Layer(WYV_SIDE_LEGS, 14, 24, 'mbody'),
        Layer(WYV_SIDE_BODY, 10, 17, 'mbody'),
    ]
    side += _wing_layers(WYV_WING_SIDE, WYV_WING_SIDE_POS)
    side += [
        Layer(pole(LANCE_HEAD, 13, grips=(9,), tail='d'), 21, 2, 'rider'),
        Layer(WYV_SIDE_HEAD, 1, 8, 'mhead'),
        Layer(RIDER_SIDE_BODY, 14, 12, 'rider', outline=True),
        Layer("""
            ......oooooo....
            ....ooWWWMMMoo..
            ...oWWMMMMMMMmo.
            ..oWMMMMMMMMMmo.
            ..oWMMMMMMMMMmo.
            ..onmmmmmmmmmno.
            .oSSeSSMMMmmo...
            .oSSeSSSMmmo....
            ..ooSSSsooo.....
        """, 10, 3, 'rhead'),
    ]
    wings_f = _wing_layers(WYV_WING_FRONT_L, WYV_WING_FRONT_POS) + \
        _wing_layers(WYV_WING_FRONT_L, WYV_WING_FRONT_POS, mirror_x=31)
    helm_f = Layer("""
        .....oooooo.....
        ...ooWWWMMMoo...
        ..oWWMMMMMMMmo..
        ..oWMMMMMMMMmo..
        .oWMMMMMMMMMmmo.
        .onmmmmmmmmmmno.
        ..oMSeSSSSesMo..
        ...oSeSSSSeso...
        ....ooSSSsoo....
    """, 8, 1, 'rhead')
    helm_b = Layer("""
        .....oooooo.....
        ...ooWWWMMMoo...
        ..oWWMMMMMMMmo..
        ..oWMMMMMMMMmo..
        .oWMMMMMMMMMmmo.
        .onmmmmmmmmmmno.
        ..oMHHHHHHhhMo..
        ...ohHHHHhhho...
        ....oohhhhoo....
    """, 8, 1, 'rhead')
    front = wings_f + [
        Layer(WYV_FRONT_LEGS, 10, 24, 'mbody'),
        Layer(WYV_FRONT_BODY, 10, 17, 'mbody'),
        Layer(RIDER_FRONT_BODY, 8, 10, 'rider', outline=True),
        Layer(pole(LANCE_HEAD, 18, grips=(8,), tail='d'), 8, 2, 'rider'),
        Layer(WYV_FRONT_HEAD, 12, 13, 'mhead'),
        helm_f,
    ]
    back = wings_f + [
        Layer(WYV_FRONT_LEGS, 10, 24, 'mbody'),
        Layer(pole(LANCE_HEAD, 18, grips=(8,), tail='d'), 21, 2, 'rider'),
        Layer(RIDER_BACK_BODY, 8, 10, 'rider', outline=True),
        Layer(WYV_BACK_BODY, 10, 17, 'mbody'),
        helm_b,
    ]
    return dict(kind='fly', mats=mats, views=dict(front=front, back=back, side=side))


MODEL_ORDER = ['lord', 'cavalier', 'hunter', 'cleric', 'knight', 'thief', 'mage', 'pegasus',
               'soldier', 'fighter', 'mercenary', 'archer', 'wyvern', 'general', 'usurper', 'civilian']

MODEL_FUNCS = {
    'lord': model_lord,
    'cavalier': model_cavalier,
    'knight': model_knight,
    'general': model_general,
    'usurper': model_usurper,
    'cleric': model_cleric,
    'mage': model_mage,
    'civilian': model_civilian,
    'soldier': model_soldier,
    'archer': model_archer,
    'fighter': model_fighter,
    'mercenary': model_mercenary,
    'thief': model_thief,
    'hunter': model_hunter,
}
MODEL_FUNCS['pegasus'] = model_pegasus
MODEL_FUNCS['wyvern'] = model_wyvern


def build_model(name):
    m = MODEL_FUNCS[name]()
    out = {}
    for anim, n in ANIM_ORDER:
        seq = ANIM_TABLES[m['kind']][anim]
        for i in range(n):
            view, keys, offs = seq[i]
            layers = m['views'][view]
            out[(anim, i)] = (layers, keys, offs, m['mats'])
    return out, m


def render_model(name, team):
    frames = {}
    built, _ = build_model(name)
    for key, (layers, keys, offs, mats) in built.items():
        frames[key] = compose(layers, keys, offs, mats, team)
    return frames


def idle_durations(kind):
    if kind == 'fly':
        return [20, 6, 20, 6]      # 飞行单位扇翅稍快
    return IDLE_DUR


def export(out_png=None, out_json=None):
    """打包：每行 = 一个 模型×阵营，15 列 = idle0-2, down0-3, up0-3, side0-3"""
    out_png = out_png or os.path.join(ASSETS, 'units.png')
    out_json = out_json or os.path.join(ASSETS, 'units.json')
    order = [(a, i) for a, n in ANIM_ORDER for i in range(n)]
    rows = [(m, t) for m in MODEL_ORDER for t in TEAMS]
    sheet = Image.new('RGBA', (len(order) * FW, len(rows) * FH), CLEAR)
    frames, anims = {}, {}
    for r, (m, t) in enumerate(rows):
        fr = render_model(m, t)
        kind = MODEL_FUNCS[m]()['kind']
        for c, (a, i) in enumerate(order):
            name = '%s_%s_%s%d' % (m, t, a, i)
            sheet.alpha_composite(fr[(a, i)], (c * FW, r * FH))
            frames[name] = [c * FW, r * FH, FW, FH, AX, AY]
        base = '%s_%s_' % (m, t)
        idur = idle_durations(kind)
        anims[base + 'idle'] = [[base + 'idle0', idur[0]], [base + 'idle1', idur[1]],
                                [base + 'idle2', idur[2]], [base + 'idle1', idur[3]]]
        for a in ('down', 'up', 'side'):
            anims[base + a] = [[base + a + str(i), WALK_DUR[i]] for i in range(4)]
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    sheet.save(out_png)
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump({'frames': frames, 'anims': anims}, f, ensure_ascii=False, separators=(',', ':'))
    return sheet, frames, anims


def preview_sheets(scale=3):
    """预览：每个模型一张（4 阵营 × 15 帧，放大 + 草地格子底），另存总览"""
    from PIL import ImageDraw
    os.makedirs(PREV, exist_ok=True)
    order = [(a, i) for a, n in ANIM_ORDER for i in range(n)]
    for m in MODEL_ORDER:
        W = len(order) * (FW + 2) + 2
        H = len(TEAMS) * (FH + 2) + 2
        img = Image.new('RGBA', (W, H), (40, 40, 52, 255))
        for r, t in enumerate(TEAMS):
            fr = render_model(m, t)
            for c, k in enumerate(order):
                bg = Image.new('RGBA', (FW, FH), (72, 110, 56, 255))
                ImageDraw.Draw(bg).rectangle([8, 16, 23, 31], fill=(84, 124, 60, 255))
                bg.alpha_composite(fr[k])
                img.paste(bg, (2 + c * (FW + 2), 2 + r * (FH + 2)))
        img.resize((W * scale, H * scale), Image.NEAREST).save(os.path.join(PREV, m + '.png'))
    # 总览：每个模型 idle0，4 阵营
    W = len(MODEL_ORDER) * (FW + 2) + 2
    H = len(TEAMS) * (FH + 2) + 2
    img = Image.new('RGBA', (W, H), (40, 40, 52, 255))
    for c, m in enumerate(MODEL_ORDER):
        for r, t in enumerate(TEAMS):
            bg = Image.new('RGBA', (FW, FH), (72, 110, 56, 255))
            ImageDraw.Draw(bg).rectangle([8, 16, 23, 31], fill=(84, 124, 60, 255))
            bg.alpha_composite(render_model(m, t)[('idle', 0)])
            img.paste(bg, (2 + c * (FW + 2), 2 + r * (FH + 2)))
    img.resize((W * scale, H * scale), Image.NEAREST).save(os.path.join(PREV, '_overview.png'))


if __name__ == '__main__':
    sheet, frames, anims = export()
    print('units.png', sheet.size, 'frames', len(frames), 'anims', len(anims))
    if '--preview' in sys.argv:
        preview_sheets()
        print('previews ->', PREV)
    seen = set()
    for w in ART_WARN:
        k = repr(w)
        if k not in seen:
            seen.add(k)
            print('WARN', w)
