#!/usr/bin/env python3
"""ORIGINAL gift-box scan target. A plain icon tracks badly, so the gift box sits on a
busy confetti background (many corners = stable tracking). Fixed seed, reproducible.
Usage: python3 make_gift_target.py <out.png> [size]"""
import math, random, sys
from PIL import Image, ImageDraw, ImageFont

out = sys.argv[1] if len(sys.argv) > 1 else "gift-target.png"
S = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
rng = random.Random(1112)
PAL = [(255,99,132),(255,193,7),(76,201,240),(129,199,132),(171,130,255),(255,138,76),(35,40,60),(255,255,255)]

img = Image.new("RGB", (S, S), (255, 244, 225))
d = ImageDraw.Draw(img)
for _ in range(260):  # confetti
    cx, cy, r = rng.randint(0, S), rng.randint(0, S), rng.randint(8, S // 18)
    col, k = rng.choice(PAL), rng.random()
    if k < 0.4: d.ellipse((cx-r, cy-r, cx+r, cy+r), fill=col)
    elif k < 0.7:
        a = rng.random() * math.pi
        d.polygon([(cx+r*math.cos(a+t), cy+r*math.sin(a+t)) for t in (0, 2.1, 4.2)], fill=col)
    else:
        a = rng.random() * math.pi
        d.line((cx, cy, cx+2*r*math.cos(a), cy+2*r*math.sin(a)), fill=col, width=rng.randint(4, 10))

# gift box (front view)
bx0, by0, bx1, by1 = S*0.22, S*0.42, S*0.78, S*0.86
ink = (35, 40, 60)
d.rectangle((bx0, by0, bx1, by1), fill=(255, 255, 255), outline=ink, width=14)
for gx in range(int(bx0)+30, int(bx1)-20, 56):          # polka dots
    for gy in range(int(by0)+40, int(by1)-20, 56):
        d.ellipse((gx-9, gy-9, gx+9, gy+9), fill=(255, 193, 7))
d.rectangle((S*0.47, by0, S*0.53, by1), fill=(255, 99, 132), outline=ink, width=10)   # ribbon
lid = (S*0.18, S*0.32, S*0.82, S*0.44)
d.rectangle(lid, fill=(255, 99, 132), outline=ink, width=14)
d.rectangle((S*0.47, S*0.32, S*0.53, S*0.44), fill=(255, 193, 7), outline=ink, width=10)
for sgn in (-1, 1):                                       # bow
    cx = S*0.5 + sgn*S*0.11
    d.ellipse((cx-S*0.1, S*0.17, cx+S*0.1, S*0.33), fill=(255, 193, 7), outline=ink, width=12)
d.ellipse((S*0.45, S*0.24, S*0.55, S*0.34), fill=(255, 99, 132), outline=ink, width=12)

d.rectangle((0, 0, S-1, S-1), outline=ink, width=S//40)
try: font = ImageFont.load_default(size=S//16)
except TypeError: font = ImageFont.load_default()
d.text((S*0.5, S*0.93), "GIFT 001", fill=ink, font=font, anchor="mm")
img.save(out); print("wrote", out)
