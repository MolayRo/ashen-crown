# -*- coding: utf-8 -*-
"""
烘焙点阵字体图集：扫描 src/ 下所有源码里出现过的字符，从 Fusion Pixel 12px BDF 里
取出对应字形，打包成 assets/font12.png（白色字形、透明底）和 src/core/fontdata.js。

用法：python tools/build_font.py        （缺字时返回码 1 并列出缺的字）
"""
import os
import sys
import json
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BDF = os.path.join(ROOT, 'tools', 'fonts', 'fusion-pixel-12px-proportional-zh_hans.bdf')
OUT_PNG = os.path.join(ROOT, 'assets', 'font12.png')
OUT_JS = os.path.join(ROOT, 'src', 'core', 'fontdata.js')

# 总是收录的字符：ASCII 可见字符 + 常用中文标点 + 界面符号
ALWAYS = ''.join(chr(c) for c in range(0x20, 0x7F))
ALWAYS += '，。、：；！？“”‘’（）《》〈〉「」『』【】…—～·．－＋×÷％￥°↑↓←→★☆●○◆◇■□▲△▼▽♪'
ALWAYS += '０１２３４５６７８９'


def parse_bdf(path):
    glyphs = {}
    cur = None
    reading = False
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if line.startswith('STARTCHAR'):
                cur = {'rows': []}
                reading = False
            elif cur is None:
                continue
            elif line.startswith('ENCODING'):
                cur['enc'] = int(line.split()[1])
            elif line.startswith('DWIDTH'):
                cur['adv'] = int(line.split()[1])
            elif line.startswith('BBX'):
                cur['bbx'] = tuple(map(int, line.split()[1:]))
            elif line == 'BITMAP':
                reading = True
            elif line == 'ENDCHAR':
                glyphs[cur['enc']] = cur
                cur = None
                reading = False
            elif reading:
                cur['rows'].append(line.strip())
    return glyphs


def collect_chars():
    chars = set(ALWAYS)
    for base in ('src', ):
        for dirpath, _, files in os.walk(os.path.join(ROOT, base)):
            for fn in files:
                if not fn.endswith(('.js', '.json', '.html')):
                    continue
                if fn == 'fontdata.js':
                    continue
                with open(os.path.join(dirpath, fn), encoding='utf-8') as f:
                    txt = f.read()
                for ch in txt:
                    if ord(ch) >= 0x20 and ch not in '\r\n\t':
                        chars.add(ch)
    for extra in ('index.html', ):
        p = os.path.join(ROOT, extra)
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                chars.update(c for c in f.read() if ord(c) >= 0x20)
    return chars


def main():
    glyphs = parse_bdf(BDF)
    chars = sorted(collect_chars(), key=ord)
    missing = [c for c in chars if ord(c) not in glyphs]
    # 表情、私用区等非文字字符不算缺字（源码注释里可能出现），只报告 CJK/标点缺失
    hard_missing = [c for c in missing if (0x2E80 <= ord(c) <= 0x9FFF) or (0xFF00 <= ord(c) <= 0xFFEF) or (0x3000 <= ord(c) <= 0x303F)]
    usable = [c for c in chars if ord(c) in glyphs]

    # 打包：固定 16px 行高的格子行，按字形实际宽度紧排
    ATLAS_W = 1024
    x, y, row_h = 0, 0, 14
    placed = {}
    for c in usable:
        g = glyphs[ord(c)]
        w, h, xo, yo = g['bbx']
        cw = max(w, 1)
        if x + cw + 1 > ATLAS_W:
            x = 0
            y += row_h
        placed[c] = (x, y, w, h, xo, yo, g['adv'])
        x += cw + 1
    atlas_h = y + row_h
    img = Image.new('RGBA', (ATLAS_W, atlas_h), (0, 0, 0, 0))
    px = img.load()
    for c, (gx, gy, w, h, xo, yo, adv) in placed.items():
        g = glyphs[ord(c)]
        for r, hexrow in enumerate(g['rows'][:h]):
            bits = int(hexrow, 16)
            nbits = len(hexrow) * 4
            for col in range(w):
                if bits & (1 << (nbits - 1 - col)):
                    px[gx + col, gy + r] = (255, 255, 255, 255)
    img.save(OUT_PNG)

    # 元数据：字符 -> [x, y, w, h, xoff, yoff, advance]
    data = {c: list(v) for c, v in placed.items()}
    js = ('// 自动生成：python tools/build_font.py —— 请勿手改\n'
          '// Fusion Pixel Font 12px (SIL OFL 1.1) https://github.com/TakWolf/fusion-pixel-font\n'
          'export const FONT_ASCENT = 10;\n'
          'export const FONT_LINE = 12;\n'
          'export const GLYPHS = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n')
    with open(OUT_JS, 'w', encoding='utf-8') as f:
        f.write(js)
    print('glyphs:', len(placed), 'atlas:', ATLAS_W, 'x', atlas_h)
    if hard_missing:
        print('MISSING:', ' '.join(hex(ord(c)) for c in hard_missing))
        sys.exit(1)
    if missing:
        print('(ignored non-text chars:', ' '.join(hex(ord(c)) for c in missing[:40]), ')')


if __name__ == '__main__':
    main()
