#!/usr/bin/env python3
"""Generate an ORIGINAL test target image for the WebAR POC.

Image tracking needs lots of distinct corners / high-contrast detail spread across
the whole picture, so this draws many random polygons, circles and lines with a
fixed seed (reproducible). Nothing here is derived from any third-party IP.

Usage: python3 make_target.py <out.png> [size]
"""
import math
import random
import sys

from PIL import Image, ImageDraw, ImageFont

out = sys.argv[1] if len(sys.argv) > 1 else "test-target-001.png"
size = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
rng = random.Random(20261111)

PALETTE = [
    (232, 76, 61), (245, 166, 35), (248, 231, 28), (126, 211, 33),
    (26, 188, 156), (52, 152, 219), (91, 73, 191), (192, 57, 243),
    (30, 30, 36), (250, 250, 245),
]

img = Image.new("RGB", (size, size), (250, 250, 245))
d = ImageDraw.Draw(img)

# Layer 1: large polygons for coarse structure
for _ in range(60):
    cx, cy = rng.randint(0, size), rng.randint(0, size)
    r = rng.randint(size // 14, size // 5)
    n = rng.randint(3, 7)
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n + rng.random() * 0.8
        rr = r * (0.5 + rng.random() * 0.7)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=rng.choice(PALETTE))

# Layer 2: small circles and rings for fine, corner-rich detail
for _ in range(220):
    cx, cy = rng.randint(0, size), rng.randint(0, size)
    r = rng.randint(6, size // 22)
    col = rng.choice(PALETTE)
    if rng.random() < 0.5:
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    else:
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=max(2, r // 4))

# Layer 3: crossing lines for edge structure
for _ in range(90):
    x1, y1 = rng.randint(0, size), rng.randint(0, size)
    ang = rng.random() * 2 * math.pi
    ln = rng.randint(size // 10, size // 3)
    d.line((x1, y1, x1 + ln * math.cos(ang), y1 + ln * math.sin(ang)),
           fill=rng.choice(PALETTE[:8] + [PALETTE[8]]), width=rng.randint(3, 9))

# Border frame (also makes the physical print edge obvious)
b = size // 40
d.rectangle((0, 0, size - 1, size - 1), outline=(30, 30, 36), width=b)

# Label plate
plate_h = size // 7
d.rectangle((size // 8, size - size // 8 - plate_h, size - size // 8, size - size // 8),
            fill=(30, 30, 36))
try:
    font = ImageFont.load_default(size=size // 14)
except TypeError:  # very old Pillow
    font = ImageFont.load_default()
d.text((size // 8 + size // 40, size - size // 8 - plate_h + size // 40),
       "AR TEST 001", fill=(250, 250, 245), font=font)

img.save(out)
print(f"wrote {out} ({size}x{size})")
