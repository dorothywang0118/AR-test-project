#!/usr/bin/env python3
"""Make a .y4m video for Chrome's fake camera: the target image printed on a
plain grey 'table', slightly rotated/scaled over time. Lets us smoke-test the whole
camera -> recognition -> 3D pipeline in headless Chrome WITHOUT a phone.
This does NOT replace real iPhone/Android testing (SRS §10.2).
Usage: make_fake_camera.py <target.png> <out.y4m>
"""
import sys, math
import numpy as np
from PIL import Image

src, out = sys.argv[1], sys.argv[2]
W, H, N = 640, 480, 60
tgt = Image.open(src).convert("RGB")
f = open(out, "wb")
f.write(f"YUV4MPEG2 W{W} H{H} F30:1 Ip A1:1 C420jpeg\n".encode())
for i in range(N):
    t = i / N
    size = int(300 + 30 * math.sin(2 * math.pi * t))
    ang = 6 * math.sin(2 * math.pi * t)
    card = tgt.resize((size, size)).rotate(ang, expand=True, fillcolor=(120, 120, 124))
    frame = Image.new("RGB", (W, H), (120, 120, 124))
    frame.paste(card, ((W - card.width) // 2, (H - card.height) // 2))
    ycc = np.asarray(frame.convert("YCbCr"), dtype=np.uint8)
    y = ycc[:, :, 0]
    cb = ycc[::2, ::2, 1]
    cr = ycc[::2, ::2, 2]
    f.write(b"FRAME\n" + y.tobytes() + cb.tobytes() + cr.tobytes())
f.close()
print("wrote", out)
