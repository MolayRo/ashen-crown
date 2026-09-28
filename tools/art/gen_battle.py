# -*- coding: utf-8 -*-
"""
《灰烬王冠》侧视战斗演出美术生成器。

用法（在项目根目录或任意目录）：
    python tools/art/gen_battle.py            # 生成全部：角色动画 + 特效 + 背景/站台
    python tools/art/gen_battle.py units      # 只生成角色动画
    python tools/art/gen_battle.py fx bg      # 只生成特效、背景
    python tools/art/gen_battle.py units elwin,glenn   # 只重画指定 set（调试用，仍写出完整图集）

产出：
    assets/battle_units.png / .json   角色战斗动画（帧 96x80，锚点 [48,76]，全部面朝左）
    assets/battle_fx.png / .json      投射物与特效（锚点在特效中心）
    assets/battle_bg.png / .json      战斗背景 320x124 + 站台 100x20
    tools/art/preview/battle/         放大预览图
"""
import os
import sys
import json
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
ASSETS = os.path.join(ROOT, 'assets')
PREV = os.path.join(HERE, 'preview', 'battle')

import numpy as np
from PIL import Image

from battle_rig import render, W, H, AX, AY
from battle_body import build_human
import battle_cast

# set 输出顺序：我方 → 敌方通用 → 首领 → 平民
ORDER = ['elwin', 'glenn', 'nora', 'serin', 'doran', 'sid', 'mira', 'vera',
         'soldier', 'fighter', 'mercenary', 'archer', 'mage_e', 'darkmage', 'knight_e', 'cavalier_e',
         'pegasus_e', 'wyvern', 'priest', 'general',
         'gord', 'hagen', 'morgan', 'grimm', 'valder',
         'martha']
ANIM_ORDER = ['idle', 'attack', 'staff', 'crit', 'ranged', 'dodge', 'hurt']

WARN = []


def render_set(name):
    S = battle_cast.SETS[name]
    L = S['look']()
    A, E = S['anims']()
    builder = S.get('builder', build_human)
    frames = []      # (frame_name, img)
    anims = {}
    for an in ANIM_ORDER:
        if an not in A:
            continue
        seq = []
        for i, (pose, dur) in enumerate(A[an]):
            F, info = builder(pose, L)
            img = render(F.parts, F.post)
            fname = '%s_%s%d' % (name, an, i)
            frames.append((fname, img))
            seq.append([fname, int(dur)])
            check_clip(fname, img)
        anims['%s_%s' % (name, an)] = seq
    events = {'%s_%s' % (name, an): ev for an, ev in E.items() if an in A}
    return frames, anims, events, dict(S['meta'])


def check_clip(fname, img):
    a = img[:, :, 3] > 0
    if a[0].any():
        WARN.append('%s 顶边被裁切' % fname)
    if a[:, 0].any() or a[:, -1].any():
        WARN.append('%s 左右边被裁切' % fname)
    if a[AY + 2:].any():
        WARN.append('%s 低于地面线 %d 行以上' % (fname, 2))


def pack(frames, cols=24):
    """96x80 等大格子排布；像素完全相同的帧共用一个格子。"""
    uniq = []
    index = {}
    rect_of = {}
    for fname, img in frames:
        h = hashlib.md5(img.tobytes()).hexdigest()
        if h not in index:
            index[h] = len(uniq)
            uniq.append(img)
        rect_of[fname] = index[h]
    rows = (len(uniq) + cols - 1) // cols
    sheet = np.zeros((rows * H, cols * W, 4), np.uint8)
    for k, img in enumerate(uniq):
        r, c = divmod(k, cols)
        sheet[r * H:(r + 1) * H, c * W:(c + 1) * W] = img
    fr = {}
    for fname, _ in frames:
        k = rect_of[fname]
        r, c = divmod(k, cols)
        fr[fname] = [c * W, r * H, W, H, AX, AY]
    return sheet, fr, len(uniq)


def preview_set(name, frames, anims):
    """每个 set 一张预览：每种动画一行，2 倍。"""
    sc = 2
    rows = [k for k in anims if k.startswith(name + '_')]
    cols = max(len(anims[k]) for k in rows)
    img = Image.new('RGBA', (cols * W * sc, len(rows) * H * sc), (32, 34, 46, 255))
    fm = dict(frames)
    for j, key in enumerate(rows):
        for i, (fname, dur) in enumerate(anims[key]):
            bg = Image.new('RGBA', (W, H), (74, 82, 100, 255))
            px = bg.load()
            for x in range(W):
                for y in range(AY + 1, H):
                    px[x, y] = (56, 62, 78, 255)
            bg.alpha_composite(Image.fromarray(fm[fname], 'RGBA'))
            img.paste(bg.resize((W * sc, H * sc), Image.NEAREST), (i * W * sc, j * H * sc))
    img.save(os.path.join(PREV, 'units_%s.png' % name))


def contact_sheet(all_frames, names):
    """总览：每个 set 的 idle0 + 攻击命中帧，1 倍排一张。"""
    fm = dict(all_frames)
    sc = 2
    cols = 6
    cell_w, cell_h = 96, 80
    per = []
    for n in names:
        picks = [n + '_idle0']
        for an in ('attack', 'staff'):
            if n + '_' + an + '0' in fm:
                picks.append(n + '_' + an + ('2' if n + '_' + an + '2' in fm else '1'))
        per.append(picks)
    rows = (len(names) + cols - 1) // cols
    img = Image.new('RGBA', (cols * 2 * cell_w * sc, rows * cell_h * sc), (32, 34, 46, 255))
    for k, picks in enumerate(per):
        r, c = divmod(k, cols)
        for t, fname in enumerate(picks[:2]):
            bg = Image.new('RGBA', (W, H), (74, 82, 100, 255))
            bg.alpha_composite(Image.fromarray(fm[fname], 'RGBA'))
            img.paste(bg.resize((W * sc, H * sc), Image.NEAREST), ((c * 2 + t) * cell_w * sc, r * cell_h * sc))
    img.save(os.path.join(PREV, 'units_overview.png'))


def gen_units(only=None):
    os.makedirs(ASSETS, exist_ok=True)
    os.makedirs(PREV, exist_ok=True)
    all_frames = []
    anims = {}
    events = {}
    sets = {}
    for name in ORDER:
        fr, an, ev, meta = render_set(name)
        all_frames += fr
        anims.update(an)
        events.update(ev)
        sets[name] = meta
        if only is None or name in only:
            preview_set(name, fr, an)
        print('  %-10s %3d 帧' % (name, len(fr)))
    sheet, frames, nu = pack(all_frames)
    Image.fromarray(sheet, 'RGBA').save(os.path.join(ASSETS, 'battle_units.png'), optimize=True)
    meta = dict(frames=frames, anims=anims, events=events, sets=sets,
                info=dict(frame=[W, H], anchor=[AX, AY], facing='left', fps=60,
                          note='所有帧面朝左；左侧（敌方）由引擎水平镜像。帧名 {set}_{anim}{i}。'))
    with open(os.path.join(ASSETS, 'battle_units.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, separators=(',', ':'))
    contact_sheet(all_frames, ORDER)
    print('battle_units: %d 帧（去重后 %d 格），图集 %dx%d' % (len(all_frames), nu, sheet.shape[1], sheet.shape[0]))


def main(argv):
    what = [a for a in argv if a in ('units', 'fx', 'bg')]
    only = None
    for a in argv:
        if a not in ('units', 'fx', 'bg'):
            only = set(a.split(','))
    if not what:
        what = ['units', 'fx', 'bg']
    if 'units' in what:
        gen_units(only)
    if 'fx' in what:
        import battle_fx
        battle_fx.generate(ASSETS, PREV)
    if 'bg' in what:
        import battle_bg
        battle_bg.generate(ASSETS, PREV)
    for w in WARN:
        print('WARN', w)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    main(sys.argv[1:])
