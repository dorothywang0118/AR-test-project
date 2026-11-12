#!/usr/bin/env python3
"""ORIGINAL scan targets: 6 gift boxes that differ in colour, pattern, ribbon style and
confetti (so the engine never confuses them). 1-5 summon one character each, 6 = group.
Usage: python3 make_gift_targets.py <out_dir> [size]   -> gift-1.png ... gift-6.png"""
import math, os, random, sys
from PIL import Image, ImageDraw, ImageFont

out = sys.argv[1] if len(sys.argv) > 1 else "."
S = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
os.makedirs(out, exist_ok=True)
INK = (35, 40, 60)
WH = (255, 255, 255)
PAL_ALL = [(255,99,132),(255,193,7),(76,201,240),(129,199,132),(171,130,255),(255,138,76),(35,40,60),(255,255,255)]

# bg, box, ribbon, accent, pattern, ribbon style, confetti palette indices (ordered per variant), seed
VARS = [
    dict(bg=(255,240,244), box=(255,99,132),  rib=(255,193,7),  acc=(255,255,255), pat="dots",    rs="cross", seed=101),
    dict(bg=(232,246,255), box=(60,140,230),  rib=(255,255,255),acc=(255,193,7),   pat="stripes", rs="v",     seed=202),
    dict(bg=(255,243,224), box=(230,60,60),   rib=(255,214,64), acc=(255,255,255), pat="checks",  rs="diag",  seed=303),
    dict(bg=(236,250,236), box=(60,170,100),  rib=(255,120,160),acc=(255,255,255), pat="zigzag",  rs="h",     seed=404),
    dict(bg=(244,238,255), box=(150,100,230), rib=(255,214,64), acc=(255,255,255), pat="stars",   rs="cross", seed=505),
    dict(bg=(255,248,214), box=(255,193,7),   rib=(230,60,120), acc=(76,201,240),  pat="rainbow", rs="cross", seed=606),
]

def confetti(d, rng, n):
    for _ in range(n):
        cx, cy, r = rng.randint(0, S), rng.randint(0, S), rng.randint(8, S // 18)
        col, k = rng.choice(PAL_ALL), rng.random()
        if k < 0.35: d.ellipse((cx-r, cy-r, cx+r, cy+r), fill=col)
        elif k < 0.65:
            a = rng.random() * math.pi
            d.polygon([(cx+r*math.cos(a+t), cy+r*math.sin(a+t)) for t in (0, 2.1, 4.2)], fill=col)
        elif k < 0.85:
            a = rng.random() * math.pi
            d.line((cx, cy, cx+2*r*math.cos(a), cy+2*r*math.sin(a)), fill=col, width=rng.randint(4, 10))
        else:
            d.rectangle((cx-r, cy-r//2, cx+r, cy+r//2), fill=col)

def star(d, cx, cy, r, col):
    pts = []
    for i in range(10):
        a = -math.pi/2 + i*math.pi/5
        rr = r if i % 2 == 0 else r*0.45
        pts.append((cx+rr*math.cos(a), cy+rr*math.sin(a)))
    d.polygon(pts, fill=col)

def pattern(d, v, bx0, by0, bx1, by1):
    p, acc = v["pat"], v["acc"]
    if p == "dots":
        for gx in range(int(bx0)+30, int(bx1)-20, 56):
            for gy in range(int(by0)+40, int(by1)-20, 56): d.ellipse((gx-9, gy-9, gx+9, gy+9), fill=(255,193,7))
    elif p == "stripes":
        for gx in range(int(bx0)+24, int(bx1)-10, 44): d.rectangle((gx, by0+8, gx+16, by1-8), fill=(30,90,180))
    elif p == "checks":
        for i, gx in enumerate(range(int(bx0)+10, int(bx1)-40, 50)):
            for j, gy in enumerate(range(int(by0)+10, int(by1)-40, 50)):
                if (i+j) % 2 == 0: d.rectangle((gx, gy, gx+50, gy+50), fill=(180,30,40))
    elif p == "zigzag":
        for gy in range(int(by0)+30, int(by1)-10, 46):
            pts = [(bx0+10+k*28, gy + (16 if k % 2 else 0)) for k in range(int((bx1-bx0-20)//28)+1)]
            d.line(pts, fill=(30,120,70), width=8)
    elif p == "stars":
        for gx in range(int(bx0)+40, int(bx1)-20, 70):
            for gy in range(int(by0)+45, int(by1)-20, 70): star(d, gx, gy, 20, (255,214,64))
    elif p == "rainbow":
        cols = [(230,60,60),(255,138,76),(129,199,132),(76,201,240),(171,130,255)]
        for i, gx in enumerate(range(int(bx0)+14, int(bx1)-30, 40)): d.rectangle((gx, by0+8, gx+26, by1-8), fill=cols[i % 5])

def make(i, v):
    rng = random.Random(v["seed"])
    img = Image.new("RGB", (S, S), v["bg"])
    d = ImageDraw.Draw(img)
    confetti(d, rng, 250 + 12*i)
    bx0, by0, bx1, by1 = S*0.22, S*0.42, S*0.78, S*0.86
    d.rectangle((bx0, by0, bx1, by1), fill=v["box"], outline=INK, width=14)
    pattern(d, v, bx0, by0, bx1, by1)
    rib, rs = v["rib"], v["rs"]
    if rs in ("cross", "v"): d.rectangle((S*0.47, by0, S*0.53, by1), fill=rib, outline=INK, width=10)
    if rs in ("cross", "h"): d.rectangle((bx0, S*0.62, bx1, S*0.68), fill=rib, outline=INK, width=10)
    if rs == "diag":
        d.polygon([(bx0, by1-60), (bx0+60, by1), (bx1, by0+60), (bx1-60, by0)], fill=rib, outline=INK)
    d.rectangle((S*0.18, S*0.32, S*0.82, S*0.44), fill=v["acc"] if v["pat"] in ("stripes","rainbow") else v["box"], outline=INK, width=14)
    d.rectangle((S*0.47, S*0.32, S*0.53, S*0.44), fill=rib, outline=INK, width=10)
    for sgn in (-1, 1):
        cx = S*0.5 + sgn*S*0.11
        d.ellipse((cx-S*0.1, S*0.17, cx+S*0.1, S*0.33), fill=rib, outline=INK, width=12)
    d.ellipse((S*0.45, S*0.24, S*0.55, S*0.34), fill=v["box"], outline=INK, width=12)
    d.rectangle((0, 0, S-1, S-1), outline=INK, width=S//40)
    try: font = ImageFont.load_default(size=S//16)
    except TypeError: font = ImageFont.load_default()
    d.text((S*0.5, S*0.93), f"GIFT 00{i+1}" if i < 5 else "GIFT ALL", fill=INK, font=font, anchor="mm")
    path = os.path.join(out, f"gift-{i+1}.png")
    img.save(path); print("wrote", path)

for i, v in enumerate(VARS):
    make(i, v)
