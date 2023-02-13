# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/collors.py
#
# File Description: class to resolve plugin dependencies
#
# By: Bast
"""
holds base color codes for ansi and xterm
"""
# Standard Library
import re

# 3rd Party

# Project

# for finding ANSI color sequences

CONVERTANSI = {}

CONVERTCOLORS = {
    'k' : '0;30',
    'r' : '0;31',
    'g' : '0;32',
    'y' : '0;33',
    'b' : '0;34',
    'm' : '0;35',
    'c' : '0;36',
    'w' : '0;37',
    'D' : '1;30',
    'R' : '1;31',
    'G' : '1;32',
    'Y' : '1;33',
    'B' : '1;34',
    'M' : '1;35',
    'C' : '1;36',
    'W' : '1;37',
    'x' : '0',
}

COLORTABLE = {}
def build_color_table():
    """
    colors 0..15: 16 basic colors
    """
    COLORTABLE[0] = (0x00, 0x00, 0x00) # 0
    COLORTABLE['k'] = COLORTABLE[0]
    COLORTABLE[1] = (0xcd, 0x00, 0x00) # 1
    COLORTABLE['r'] = COLORTABLE[1]
    COLORTABLE[2] = (0x00, 0xcd, 0x00) # 2
    COLORTABLE['g'] = COLORTABLE[2]
    COLORTABLE[3] = (0xcd, 0xcd, 0x00) # 3
    COLORTABLE['y'] = COLORTABLE[3]
    COLORTABLE[4] = (0x00, 0x00, 0xee) # 4
    COLORTABLE['b'] = COLORTABLE[4]
    COLORTABLE[5] = (0xcd, 0x00, 0xcd) # 5
    COLORTABLE['m'] = COLORTABLE[5]
    COLORTABLE[6] = (0x00, 0xcd, 0xcd) # 6
    COLORTABLE['c'] = COLORTABLE[6]
    COLORTABLE[7] = (0xe5, 0xe5, 0xe5) # 7
    COLORTABLE['w'] = COLORTABLE[7]
    COLORTABLE[8] = (0x7f, 0x7f, 0x7f) # 8
    COLORTABLE['D'] = COLORTABLE[8]
    COLORTABLE[9] = (0xff, 0x00, 0x00) # 9
    COLORTABLE['R'] = COLORTABLE[9]
    COLORTABLE[10] = (0x00, 0xff, 0x00) # 10
    COLORTABLE['G'] = COLORTABLE[10]
    COLORTABLE[11] = (0xff, 0xff, 0x00) # 11
    COLORTABLE['Y'] = COLORTABLE[11]
    COLORTABLE[12] = (0x5c, 0x5c, 0xff) # 12
    COLORTABLE['B'] = COLORTABLE[12]
    COLORTABLE[13] = (0xff, 0x00, 0xff) # 13
    COLORTABLE['M'] = COLORTABLE[13]
    COLORTABLE[14] = (0x00, 0xff, 0xff) # 14
    COLORTABLE['C'] = COLORTABLE[14]
    COLORTABLE[15] = (0xff, 0xff, 0xff) # 15
    COLORTABLE['W'] = COLORTABLE[15]

    # colors 16..232: the 6x6x6 color cube

    valuerange = (0x00, 0x5f, 0x87, 0xaf, 0xd7, 0xff)

    for i in range(217):
        red = valuerange[(i // 36) % 6]
        green = valuerange[(i // 6) % 6]
        blue = valuerange[i % 6]
        COLORTABLE[i + 16] = ((red, green, blue))

    # colors 233..253: grayscale

    for i in range(1, 22):
        gray = 8 + i * 10
        COLORTABLE[i + 233] = ((gray, gray, gray))

build_color_table()

for colorc in CONVERTCOLORS:
    CONVERTANSI[CONVERTCOLORS[colorc]] = colorc

#xterm colors
for xtn in range(0, 256):
    CONVERTANSI['38;5;%d' % xtn] = 'x%d' % xtn
    CONVERTANSI['48;5;%d' % xtn] = 'z%d' % xtn

#backgrounds
for acn in range(40, 48):
    CONVERTANSI['%s' % acn] = CONVERTANSI['48;5;%d' % (acn - 40)]

#foregrounds
for abn in range(30, 38):
    CONVERTANSI['%s' % abn] = CONVERTANSI['0;%d' % abn]
