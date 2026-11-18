#!/usr/bin/env python3
"""fb_load 用の起動ロゴ (16bit RGB565 BMP, 170x320) を作る。
fb_load は縦長画像を 90 度回して 320x170 の内蔵液晶に出すため、先に 90 度回しておく。
使い方: make_splash.py <出力パス> [元画像]
"""
import os, struct, sys
from PIL import Image
out = sys.argv[1]
src = sys.argv[2] if len(sys.argv) > 2 else '/usr/share/APPLaunch/share/images/lockscreen.png'
W, H = 320, 170
canvas = Image.new('RGB', (W, H), (0, 0, 0))
if os.path.exists(src):
    im = Image.open(src).convert('RGB'); im.thumbnail((W, H))
    canvas.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
canvas = canvas.rotate(90, expand=True)        # -> 170x320
W, H = canvas.size
px = canvas.load()
data = bytearray()
for y in range(H - 1, -1, -1):                 # BMP は下の行から
    for x in range(W):
        r, g, b = px[x, y]
        data += struct.pack('<H', ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
    data += b'\0' * ((4 - (W * 2) % 4) % 4)
off = 14 + 40 + 12
fh = struct.pack('<2sIHHI', b'BM', off + len(data), 0, 0, off)
ih = struct.pack('<IiiHHIIiiII', 40, W, H, 1, 16, 3, len(data), 2835, 2835, 0, 0)
masks = struct.pack('<III', 0xF800, 0x07E0, 0x001F)
open(out, 'wb').write(fh + ih + masks + data)
print('splash:', out, W, 'x', H)
