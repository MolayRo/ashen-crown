# -*- coding: utf-8 -*-
"""
《灰烬王冠》主调色板 —— 所有美术生成脚本共用。
规则：
  * 每个色阶从暗到亮排列（index 0 最暗）。
  * 描边统一用 INK（近黑紫）或该材质色阶的最暗色；不要用纯黑 #000000。
  * 光源来自左上方：左上亮、右下暗。
  * 不要使用抗锯齿/半透明像素（特效除外），不要在色阶外随意取色。
"""

def hx(s):
    s = s.lstrip('#')
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)

INK = hx('#120e1c')        # 通用外描边
INK2 = hx('#2a2238')       # 次级描边/深阴影
CLEAR = (0, 0, 0, 0)

RAMPS = {
    # 中性灰（冷）
    'grey':    ['#3c3a50', '#5d5b72', '#8a8aa0', '#b8b9c8', '#e6e7ef', '#ffffff'],
    # 皮肤（亮肤）: 描边色, 深阴影, 阴影, 基色, 高光
    'skin':    ['#5a2f2a', '#a45a44', '#d98a6a', '#f2b896', '#fde0c4'],
    'skin_dk': ['#3e2016', '#7a4a36', '#b67b58', '#d8a07a', '#eec29a'],
    'skin_old':['#4e2c26', '#94604c', '#c88e72', '#e6b496', '#f6d4bc'],
    # 发色
    'hair_brown':  ['#2a180e', '#3a2418', '#6a4028', '#9a6438', '#c89058'],
    'hair_blonde': ['#4a3010', '#6a4a18', '#b08428', '#e0bc48', '#fff09a'],
    'hair_ash':    ['#4a4238', '#7a7058', '#b0a67e', '#dcd4a8', '#fbf6dc'],   # 艾尔文：灰金
    'hair_red':    ['#2e0c10', '#4a1418', '#8a2424', '#c8403a', '#f07860'],
    'hair_black':  ['#0c0e18', '#141828', '#283048', '#404c70', '#6878a0'],
    'hair_silver': ['#3a4050', '#5a6070', '#9aa2b4', '#d0d6e2', '#ffffff'],
    'hair_grey':   ['#2e2c30', '#4c4a50', '#7a7880', '#a8a6ae', '#d4d2d8'],
    'hair_purple': ['#1c1030', '#2a1840', '#4c2c70', '#7a4aa8', '#b08ad8'],
    'hair_lav':    ['#2c2040', '#4a3a6a', '#7a68a0', '#aa9ccc', '#dcd4f0'],   # 米拉：浅紫
    # 阵营色（地图/战斗中的敌我识别）
    'team_blue':  ['#101a38', '#182448', '#28407c', '#3c64b8', '#6c9ce8', '#b0d0ff'],
    'team_red':   ['#300c10', '#481418', '#7c2424', '#b83c30', '#e8705c', '#ffb8a0'],
    'team_green': ['#0e2412', '#183a20', '#28602c', '#3c9040', '#78c060', '#c0f0a0'],
    'team_grey':  ['#1e1e26', '#2e2e38', '#4a4a56', '#6e6e7c', '#9a9aa6', '#c8c8d0'],
    # 材质
    'steel':   ['#22262e', '#3a4050', '#6a7488', '#a4aebe', '#dfe6ee'],
    'iron':    ['#1a1a20', '#2c2c36', '#4a4a58', '#707080', '#9c9cac'],
    'gold':    ['#3a2408', '#5a3a10', '#a06a18', '#e0a830', '#ffe07a'],
    'leather': ['#24160c', '#3a2414', '#6a4424', '#9a6a3a', '#c89a60'],
    'wood':    ['#2a1a10', '#4a3020', '#7a5230', '#a87a48', '#d0a870'],
    'cloth_white': ['#5a5e72', '#8a90a8', '#c0c6d8', '#e8ecf4', '#ffffff'],
    'cloth_navy':  ['#0c1026', '#16204a', '#243470', '#34509a', '#5a78c0'],
    'cloth_green': ['#0e2014', '#1a3a22', '#2a5a30', '#40803e', '#68a85a'],
    'cloth_olive': ['#1e1e10', '#343418', '#545428', '#7a7a3e', '#a4a45e'],
    'cloth_teal':  ['#081e22', '#10343a', '#1c545a', '#2c7a7e', '#52a8a4'],
    'cloth_crimson': ['#200810', '#3e0e1a', '#6a1826', '#9a2434', '#c8424a'],
    'cloth_purple':  ['#160c20', '#2a1638', '#442458', '#643a80', '#8a5aa8'],
    'cloth_brown':   ['#1e140c', '#34241a', '#54402c', '#7a6040', '#a08460'],
    'cloth_black':   ['#08080c', '#121218', '#1e1e28', '#2e2e3c', '#444456'],
    'cloth_sky':     ['#1a2c48', '#2c4a70', '#4a78a8', '#7aa8d4', '#b8daf4'],
    # 自然
    'grass':   ['#1e4020', '#2c5a28', '#3e7a30', '#5c9a3a', '#84b84a', '#b0d468'],
    'forest':  ['#0c2418', '#173a24', '#245232', '#3a6e3c', '#58904a'],
    'water':   ['#10244c', '#1c3a78', '#2858a8', '#3c7cd0', '#6aa8e8', '#b8e0ff'],
    'earth':   ['#3a2818', '#5a4028', '#8a6a44', '#b89a68', '#dcc890'],
    'rock':    ['#2e2420', '#4a3a34', '#6e5a4a', '#9a8468', '#c8b490', '#e8dcc0'],
    'snow':    ['#5a6a8a', '#8a9ab8', '#b8c8e0', '#dde8f5', '#ffffff'],
    'stone':   ['#22202c', '#3a3848', '#5a586c', '#7e7c92', '#a8a6b8', '#cfcedc'],
    'roof_red':  ['#2e0e0e', '#5a1c1c', '#8e2e28', '#c04a38', '#e07a58'],
    'roof_blue': ['#0e1430', '#1c2c5a', '#2c4a8e', '#4a6ab8', '#7a98d8'],
    'fire':    ['#5a1808', '#c84010', '#f08020', '#ffd040', '#fff4b0'],
    'carpet':  ['#2a0610', '#5a1020', '#8c1c30', '#c03048', '#e05868'],
    'magic_blue': ['#101848', '#2040a0', '#4080e0', '#90c8ff', '#e8f8ff'],
    'magic_dark': ['#10061c', '#2c0c40', '#5a1a78', '#9a40b8', '#e0a0f0'],
    'heal':    ['#1a4a30', '#2a8a50', '#60d080', '#b0f8c0', '#f0fff0'],
    'eye_blue':   ['#101838', '#28407c', '#4a7ad0', '#9ac4ff'],
    'eye_green':  ['#0e2014', '#2a5a30', '#4ea060', '#a0e0a0'],
    'eye_brown':  ['#1a0e08', '#4a2a18', '#8a5a30', '#d0a068'],
    'eye_violet': ['#1a0e2c', '#44246a', '#7a4ab0', '#c8a0f0'],
    'eye_amber':  ['#2a1404', '#6a3a0c', '#c07a18', '#f8c860'],
    'eye_grey':   ['#16181e', '#3a3e48', '#6a707e', '#b0b6c4'],
    'eye_ice':    ['#0e2030', '#2a5a7a', '#5aa0c8', '#c0ecff'],
    'eye_gold':   ['#2a1c04', '#6a4a0c', '#c09018', '#fff0a0'],
    'eye_red':    ['#200408', '#5a0c14', '#b02030', '#ff8080'],
}

PAL = {k: [hx(c) for c in v] for k, v in RAMPS.items()}


def ramp(name, i):
    r = PAL[name]
    i = max(0, min(len(r) - 1, i))
    return r[i]


def team_swap(img, src='team_blue', dst='team_red'):
    """把图像中 src 色阶的像素逐一替换成 dst 色阶（阵营换色）。"""
    from PIL import Image
    a, b = PAL[src], PAL[dst]
    mapping = {a[i][:3]: b[i] for i in range(min(len(a), len(b)))}
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            p = px[x, y]
            if p[3] and p[:3] in mapping:
                px[x, y] = mapping[p[:3]]
    return out


def preview(img, path, scale=4, bg=(40, 40, 52, 255)):
    """把像素图放大保存，方便用图片查看器检查。"""
    from PIL import Image
    base = Image.new('RGBA', img.size, bg)
    base.alpha_composite(img)
    base.resize((img.width * scale, img.height * scale), Image.NEAREST).save(path)
