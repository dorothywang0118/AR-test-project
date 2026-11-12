#!/usr/bin/env python3
"""Build ORIGINAL chibi test characters (5 store staff, ids A-E) as binary glTF (.glb).

Each model has 8 animation clips:
  Idle (loop), Pat (head-pat), HighFive, Cry (crouch crying), Sway (happy head swing),
  Angry (hands on hips), Think (chin on hands, excited), Flop (collapsed on the floor).

Pure stdlib + struct. Parts are low-poly ellipsoids / boxes; expressions and props are
nodes whose scale is toggled by STEP animation tracks (hidden = tiny scale).
Y up, front = +Z, feet at y=0, height ~1.0 unit (then scaled by relative height).

Usage: python3 make_chibi_glb.py <out_dir>      # writes char-a.glb ... char-e.glb
"""
import json
import math
import os
import struct
import sys

HID = [0.001, 0.001, 0.001]
SKIN, INK, BLUSH, RED, TONGUE = "#fbdfc9", "#26232b", "#f5a3a3", "#c93a4a", "#f08a95"
SLEEVE_PROP, WHITE = "#a9c9e8", "#ffffff"
S = 1 / 228.0  # 2D sheet pixels -> model units

CHARS = {
    "a": dict(h=168, bw=0.95, hair="#1f1c22", style="long8", glasses="thick", tee="#ec8fb5", jacket=None,
              pants="#4f78b5", shoes="#2b2b30", flopdir=-1),
    "b": dict(h=170, bw=0.90, hair="#3b2a22", style="jp", glasses="kimu", tee="#2a2a30", jacket="#2e2e36", hood=True,
              pants="#33333b", shoes="#222222", flopdir=-1),
    "c": dict(h=180, bw=1.10, hair="#1b1a20", style="short", glasses="thin", tee="#8a8f98", jacket="#d9361f",
              pants="#4a4f3d", shoes="#2b2b30", flopdir=-1),
    "d": dict(h=166, bw=0.90, hair="#6b4630", style="wavy", glasses=None, tee="#b8bcc4", jacket="#34343e",
              pants="#26262c", shoes="#222222", bag="#5f7447", wide=True, flopdir=1),
    "e": dict(h=150, bw=1.00, hair="#1f1c22", style="bun", glasses=None, tee="#ffffff", jacket="#ece1c3",
              collar="#b98a4e", pants="#4f78b5", shoes="#9bb6cf", flopdir=1),
}


def kf(h):  # same exaggerated height scale as the confirmed sheet (v6)
    return 1.14 if h >= 180 else 1 - (180 - h) * 0.007


# ------------------------------------------------------------------ math helpers
def hex_rgba(c):
    c = c.lstrip("#")
    return [int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4)] + [1.0]


def srgb_to_lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def qz(a):
    return (0.0, 0.0, math.sin(a / 2), math.cos(a / 2))


def qx(a):
    return (math.sin(a / 2), 0.0, 0.0, math.cos(a / 2))


def qy(a):
    return (0.0, math.sin(a / 2), 0.0, math.cos(a / 2))


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


# ------------------------------------------------------------------ geometry
def ellipsoid(rx, ry, rz, nt=10, np_=14, t0=0.0, t1=math.pi):
    pos, nor, idx = [], [], []
    for i in range(nt + 1):
        t = t0 + (t1 - t0) * i / nt
        for j in range(np_ + 1):
            p = 2 * math.pi * j / np_
            x, y, z = math.sin(t) * math.sin(p), math.cos(t), math.sin(t) * math.cos(p)
            pos.append((rx * x, ry * y, rz * z))
            n = (x / rx, y / ry, z / rz)
            l = math.sqrt(sum(c * c for c in n)) or 1
            nor.append(tuple(c / l for c in n))
    for i in range(nt):
        for j in range(np_):
            a, b = i * (np_ + 1) + j, i * (np_ + 1) + j + 1
            c, d = a + np_ + 1, b + np_ + 1
            idx += [a, c, b, b, c, d]
    return pos, nor, idx


def box(sx, sy, sz):
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    faces = [
        ((0, 0, 1), [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]),
        ((0, 0, -1), [(hx, -hy, -hz), (-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz)]),
        ((1, 0, 0), [(hx, -hy, hz), (hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz)]),
        ((-1, 0, 0), [(-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz)]),
        ((0, 1, 0), [(-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz), (-hx, hy, -hz)]),
        ((0, -1, 0), [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)]),
    ]
    pos, nor, idx = [], [], []
    for n, cs in faces:
        b = len(pos)
        for c in cs:
            pos.append(c)
            nor.append(n)
        idx += [b, b + 1, b + 2, b, b + 2, b + 3]
    return pos, nor, idx


# ------------------------------------------------------------------ glTF builder
class Builder:
    def __init__(self):
        self.nodes, self.meshes, self.mats, self.matidx = [], [], [], {}
        self.bin = bytearray()
        self.views, self.accs = [], []
        self.mesh_cache = {}
        self.anims = []
        self.byname = {}

    # -- binary
    def view(self, data, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        v = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            v["target"] = target
        self.bin.extend(data)
        self.views.append(v)
        return len(self.views) - 1

    def acc(self, view, comp, count, typ, mn=None, mx=None):
        a = {"bufferView": view, "componentType": comp, "count": count, "type": typ}
        if mn is not None:
            a["min"], a["max"] = mn, mx
        self.accs.append(a)
        return len(self.accs) - 1

    def material(self, color):
        if color not in self.matidx:
            rgba = hex_rgba(color)
            rgba = [srgb_to_lin(c) for c in rgba[:3]] + [1.0]
            self.mats.append({"name": "m" + color.lstrip("#"), "pbrMetallicRoughness": {
                "baseColorFactor": rgba, "metallicFactor": 0.0, "roughnessFactor": 0.85}})
            self.matidx[color] = len(self.mats) - 1
        return self.matidx[color]

    def mesh(self, key, geom, color):
        k = (key, color)
        if k in self.mesh_cache:
            return self.mesh_cache[k]
        pos, nor, idx = geom
        pv = self.view(b"".join(struct.pack("<3f", *p) for p in pos), 34962)
        nv = self.view(b"".join(struct.pack("<3f", *n) for n in nor), 34962)
        iv = self.view(b"".join(struct.pack("<H", i) for i in idx), 34963)
        xs, ys, zs = zip(*pos)
        pa = self.acc(pv, 5126, len(pos), "VEC3", [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)])
        na = self.acc(nv, 5126, len(nor), "VEC3")
        ia = self.acc(iv, 5123, len(idx), "SCALAR")
        self.meshes.append({"primitives": [{"attributes": {"POSITION": pa, "NORMAL": na}, "indices": ia,
                                            "material": self.material(color)}]})
        self.mesh_cache[k] = len(self.meshes) - 1
        return self.mesh_cache[k]

    # -- scene graph
    def node(self, name, parent=None, t=None, r=None, s=None, mesh=None):
        assert name not in self.byname, name
        n = {"name": name}
        if t:
            n["translation"] = list(t)
        if r:
            n["rotation"] = list(r)
        if s:
            n["scale"] = list(s)
        if mesh is not None:
            n["mesh"] = mesh
        self.nodes.append(n)
        i = len(self.nodes) - 1
        self.byname[name] = i
        if parent is not None:
            self.nodes[self.byname[parent]].setdefault("children", []).append(i)
        return name

    def part(self, name, parent, kind, dims, color, t=None, r=None, s=None, **kw):
        if kind == "ell":
            geom = ellipsoid(*dims, **kw)
        else:
            geom = box(*dims)
        key = (kind, tuple(round(d, 5) for d in dims), tuple(sorted(kw.items())))
        return self.node(name, parent, t, r, s, self.mesh(key, geom, color))

    # -- animation
    def anim(self, name, tracks):
        samplers, channels = [], []
        for node, path, times, values, interp in tracks:
            tv = self.view(b"".join(struct.pack("<f", x) for x in times))
            ta = self.acc(tv, 5126, len(times), "SCALAR", [min(times)], [max(times)])
            flat = [c for v in values for c in v]
            ov = self.view(b"".join(struct.pack("<f", c) for c in flat))
            typ = {"translation": "VEC3", "rotation": "VEC4", "scale": "VEC3"}[path]
            oa = self.acc(ov, 5126, len(values), typ)
            samplers.append({"input": ta, "output": oa, "interpolation": interp})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": self.byname[node], "path": path}})
        self.anims.append({"name": name, "samplers": samplers, "channels": channels})

    def write(self, path, root_name):
        gltf = {"asset": {"version": "2.0", "generator": "store-ar-platform/tools/make_chibi_glb.py"},
                "scene": 0, "scenes": [{"nodes": [self.byname[root_name]]}], "nodes": self.nodes,
                "meshes": self.meshes, "materials": self.mats, "animations": self.anims,
                "accessors": self.accs, "bufferViews": self.views, "buffers": [{"byteLength": len(self.bin)}]}
        js = json.dumps(gltf, separators=(",", ":")).encode()
        js += b" " * (-len(js) % 4)
        while len(self.bin) % 4:
            self.bin.append(0)
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        with open(path, "wb") as f:
            f.write(struct.pack("<III", 0x46546C67, 2, total))
            f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
            f.write(struct.pack("<II", len(self.bin), 0x004E4942) + bytes(self.bin))
        return total


# ------------------------------------------------------------------ character
HEAD_C = (0.0, 0.693, 0.0)  # head ellipsoid centre in model space
HEAD_R = (0.281, 0.246, 0.25)
NECK_Y = 0.447  # head pivot (chin level)
HEAD_LOCAL_Y = HEAD_C[1] - NECK_Y  # centre of head relative to pivot


def surf_z(x, yl):
    """z of the head surface at head-local (x, y) where y is relative to the HEAD centre."""
    v = 1 - (x / HEAD_R[0]) ** 2 - (yl / HEAD_R[1]) ** 2
    return HEAD_R[2] * math.sqrt(max(v, 0.0))


def build(cid, c):
    b = Builder()
    bw = c["bw"]
    sleeve = c.get("jacket") or c["tee"]
    scale = kf(c["h"]) / 0.96
    b.node("Scaler", None, s=[scale] * 3)
    b.node("Root", "Scaler")
    b.node("Upper", "Root")

    # ---- legs & shoes
    legx = 0.061 * bw * (1.25 if c.get("wide") else 1.0)
    for side, sx in (("L", -1), ("R", 1)):
        b.node(f"Leg{side}", "Root", t=[sx * legx, 0, 0])
        w = 0.046 * (1.25 if c.get("wide") else 1.0)
        b.part(f"LegMesh{side}", f"Leg{side}", "ell", (w, 0.118, w), c["pants"], t=[0, 0.118, 0])
        b.part(f"Shoe{side}", "Root", "ell", (0.066, 0.03, 0.088), c["shoes"], t=[sx * legx, 0.026, 0.03])

    # ---- torso
    b.part("Torso", "Upper", "ell", (0.145 * bw, 0.14, 0.105), sleeve, t=[0, 0.338, 0])
    if c.get("jacket"):
        b.part("TeeStrip", "Upper", "box", (0.07 * bw, 0.25, 0.012), c["tee"], t=[0, 0.33, 0.1])
    if c.get("hood"):
        b.part("Hood", "Upper", "ell", (0.13 * bw, 0.05, 0.1), "#3b3b46", t=[0, 0.45, 0.0])
    if c.get("collar"):
        for sx in (-1, 1):
            b.part(f"Collar{sx}", "Upper", "box", (0.04, 0.06, 0.012), c["collar"], t=[sx * 0.03, 0.44, 0.1],
                   r=qz(-sx * 0.5))
    if c.get("bag"):
        b.part("BagStrap", "Upper", "box", (0.014, 0.3, 0.014), c["bag"], t=[0, 0.34, 0.105], r=qz(-0.7))
        b.part("Bag", "Upper", "box", (0.085, 0.07, 0.04), c["bag"], t=[0.11 * bw, 0.25, 0.09])

    # ---- arms (2 segments)
    shx = 0.114 * bw
    for side, sx in (("L", -1), ("R", 1)):
        b.node(f"Arm{side}", "Upper", t=[sx * shx, 0.421, 0], r=qz(sx * 0.25))
        b.part(f"ArmMesh{side}", f"Arm{side}", "ell", (0.036, 0.056, 0.036), sleeve, t=[0, -0.045, 0])
        b.node(f"Fore{side}", f"Arm{side}", t=[0, -0.09, 0])
        b.part(f"ForeMesh{side}", f"Fore{side}", "ell", (0.033, 0.053, 0.033), sleeve, t=[0, -0.04, 0])
        if c.get("collar"):
            b.part(f"Cuff{side}", f"Fore{side}", "ell", (0.035, 0.022, 0.035), c["collar"], t=[0, -0.07, 0])
        b.part(f"Hand{side}", f"Fore{side}", "ell", (0.04, 0.04, 0.04), SKIN, t=[0, -0.096, 0])

    # ---- head
    b.node("Head", "Upper", t=[0, NECK_Y, 0])
    b.part("Skull", "Head", "ell", HEAD_R, SKIN, t=[0, HEAD_LOCAL_Y, 0], nt=14, np_=20)
    build_hair(b, c)
    build_face(b, c)

    # ---- props
    build_props(b)
    build_anims(b, c)
    return b


def seg(b, name, parent, p1, p2, th, color, flat_z=None):
    """Thin box from p1 to p2 (head-local x,y) at depth z."""
    (x1, y1), (x2, y2) = p1, p2
    L = math.hypot(x2 - x1, y2 - y1)
    ang = math.atan2(y2 - y1, x2 - x1)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    z = flat_z if flat_z is not None else surf_z(mx, my - HEAD_LOCAL_Y) + 0.006
    return b.part(name, parent, "box", (L, th, 0.012), color, t=[mx, my, z], r=qz(ang))


def build_hair(b, c):
    h, st = c["hair"], c["style"]
    hy = HEAD_LOCAL_Y
    t1 = {"short": 1.12, "long8": 1.12, "jp": 1.15, "wavy": 1.1, "bun": 1.15}[st]
    b.part("HairDome", "Head", "ell", (0.292, 0.266, 0.262), h, t=[0, hy + 0.008, -0.012], nt=10, np_=18, t0=0, t1=t1)
    if st in ("long8", "wavy"):
        # long back hair
        if st == "long8":
            b.part("HairBack", "Head", "box", (0.5, 0.5, 0.08), h, t=[0, hy - 0.12, -0.19])
            for sx in (-1, 1):
                b.part(f"HairSide{sx}", "Head", "box", (0.07, 0.42, 0.2), h, t=[sx * 0.265, hy - 0.1, -0.06])
            for sx in (-1, 1):  # 八字 bangs: two slanted slabs meeting at the centre part
                b.part(f"Bang{sx}", "Head", "box", (0.2, 0.05, 0.05), h, t=[sx * 0.1, hy + 0.115, 0.205],
                       r=qz(-sx * 0.32))
        else:
            pts = [(-0.27, 0.0), (-0.28, -0.1), (-0.26, -0.2), (-0.2, -0.3), (-0.1, -0.33), (0.0, -0.34),
                   (0.1, -0.33), (0.2, -0.3), (0.26, -0.2), (0.28, -0.1), (0.27, 0.0), (-0.24, 0.08), (0.24, 0.08)]
            for i, (x, y) in enumerate(pts):
                b.part(f"Curl{i}", "Head", "ell", (0.055, 0.055, 0.055), h, t=[x, hy + 0.0 + y, -0.07 + (0.0 if abs(x) < 0.2 else 0.04)],
                       nt=6, np_=8)
            b.part("Fringe", "Head", "box", (0.46, 0.06, 0.06), h, t=[0, hy + 0.13, 0.2])
    if st == "jp":
        for i, x in enumerate((-0.2, -0.1, 0.0, 0.1, 0.2)):
            b.part(f"Tooth{i}", "Head", "box", (0.07, 0.07, 0.04), h, t=[x, hy + 0.135 - (0.015 if i % 2 else 0), 0.21],
                   r=qz(math.pi / 4))
    if st == "bun":
        b.part("Bun", "Head", "ell", (0.075, 0.075, 0.075), h, t=[0, hy + 0.27, -0.03])


def build_face(b, c):
    hy = HEAD_LOCAL_Y
    ey, my = 0.211 - 0.0 + (0.0), 0.12  # eye / mouth heights, head-local (relative to pivot)
    # convert: face features are positioned in head-local space around pivot, i.e. y relative to NECK.
    # eye world y .658 -> local .211 ; mouth world ~.565 -> local .118 ; brows .737 -> .29
    exs = 0.0965
    ez = surf_z(exs, ey - hy) + 0.004
    # ---- always on: blush
    for sx in (-1, 1):
        b.part(f"Blush{sx}", "Head", "ell", (0.033, 0.018, 0.01), BLUSH, t=[sx * 0.165, 0.131, surf_z(0.165, 0.131 - hy) + 0.002],
               nt=6, np_=10)

    def group(name, vis):
        b.node(name, "Head", s=None if vis else HID)
        return name

    # ---- eyes
    g = group("EyesOpen", True)
    for sx in (-1, 1):
        b.part(f"EO{sx}", g, "ell", (0.027, 0.034, 0.012), INK, t=[sx * exs, ey, ez], nt=8, np_=12)
        b.part(f"EOh{sx}", g, "ell", (0.009, 0.01, 0.006), WHITE, t=[sx * exs + 0.01, ey + 0.012, ez + 0.01], nt=5, np_=8)
    g = group("EyesStar", False)
    for sx in (-1, 1):
        b.part(f"ES{sx}", g, "ell", (0.037, 0.043, 0.012), INK, t=[sx * exs, ey, ez], nt=8, np_=12)
        b.part(f"ESh{sx}", g, "ell", (0.014, 0.015, 0.006), WHITE, t=[sx * exs + 0.014, ey + 0.017, ez + 0.01], nt=5, np_=8)
        b.part(f"ESg{sx}", g, "ell", (0.007, 0.008, 0.006), WHITE, t=[sx * exs - 0.014, ey - 0.018, ez + 0.01], nt=5, np_=8)
    g = group("EyesHappy", False)
    for sx in (-1, 1):
        x = sx * exs
        seg(b, f"EH{sx}a", g, (x - 0.04, ey - 0.012), (x, ey + 0.018), 0.012, INK)
        seg(b, f"EH{sx}b", g, (x, ey + 0.018), (x + 0.04, ey - 0.012), 0.012, INK)
    g = group("EyesCry", False)
    for sx in (-1, 1):
        x = sx * exs
        a, bb = (x - sx * 0.04, ey + 0.032), (x + sx * 0.04, ey)
        seg(b, f"EC{sx}a", g, a, bb, 0.012, INK)
        seg(b, f"EC{sx}b", g, bb, (x - sx * 0.04, ey - 0.032), 0.012, INK)
    g = group("EyesX", False)
    for sx in (-1, 1):
        x = sx * exs
        seg(b, f"EX{sx}a", g, (x - 0.035, ey + 0.035), (x + 0.035, ey - 0.035), 0.012, INK)
        seg(b, f"EX{sx}b", g, (x - 0.035, ey - 0.035), (x + 0.035, ey + 0.035), 0.012, INK)
    g = group("BrowsAngry", False)
    for sx in (-1, 1):
        seg(b, f"BA{sx}", g, (sx * 0.15, 0.305), (sx * 0.04, 0.268), 0.02, INK)

    # ---- mouth
    def arc(name, g, up, y0, w=0.055, d=0.022):
        pts = []
        for i in range(5):
            x = -w + 2 * w * i / 4
            y = y0 - d * (1 - (x / w) ** 2) if up else y0 + d * (1 - (x / w) ** 2)
            pts.append((x, y))
        for i in range(4):
            seg(b, f"{name}{i}", g, pts[i], pts[i + 1], 0.011, INK)

    g = group("MouthSmile", True)
    arc("MS", g, True, 0.125 + 0.012)
    g = group("MouthOpen", False)
    b.part("MOr", g, "ell", (0.05, 0.036, 0.012), RED, t=[0, 0.115, surf_z(0, 0.115 - hy) + 0.004], nt=8, np_=14)
    b.part("MOt", g, "ell", (0.026, 0.014, 0.008), TONGUE, t=[0, 0.1, surf_z(0, 0.1 - hy) + 0.01], nt=6, np_=10)
    g = group("MouthFrown", False)
    arc("MF", g, False, 0.1, 0.05, 0.02)
    g = group("MouthWail", False)
    b.part("MWr", g, "ell", (0.04, 0.045, 0.012), RED, t=[0, 0.108, surf_z(0, 0.108 - hy) + 0.004], nt=8, np_=14)
    g = group("MouthFlat", False)
    seg(b, "MFl", g, (-0.04, 0.12), (0.04, 0.12), 0.011, INK)
    b.part("Tongue", g, "ell", (0.022, 0.04, 0.01), TONGUE, t=[0.012, 0.092, surf_z(0, 0.092 - hy) + 0.004], nt=6, np_=10)

    # ---- glasses
    gl = c.get("glasses")
    if gl:
        th, col, top = {"thick": (0.022, INK, 0.022), "thin": (0.009, INK, 0.009), "kimu": (0.011, "#3c3c46", 0.02)}[gl]
        zf = surf_z(exs, ey - hy) + 0.016
        w, hh = 0.167, 0.123
        for sx in (-1, 1):
            x0, x1, y0, y1 = sx * exs - w / 2, sx * exs + w / 2, ey - hh / 2, ey + hh / 2
            seg(b, f"GT{sx}", "Head", (x0, y1), (x1, y1), top, col, flat_z=zf)
            seg(b, f"GB{sx}", "Head", (x0, y0), (x1, y0), th, col, flat_z=zf)
            seg(b, f"GL{sx}", "Head", (x0, y0), (x0, y1), th, col, flat_z=zf)
            seg(b, f"GR{sx}", "Head", (x1, y0), (x1, y1), th, col, flat_z=zf)
            # temple arm going back along the head
            xo = sx * (exs + w / 2)
            L = 0.17
            b.part(f"GA{sx}", "Head", "box", (th, th, L), col, t=[sx * 0.265, ey + 0.004, zf - L / 2 - 0.03], r=qy(sx * 0.0))
        seg(b, "GBr", "Head", (-0.015, ey + 0.03), (0.015, ey + 0.03), th, col, flat_z=zf)


def heart(b, name, parent, color="#f26b8a"):
    b.node(name, parent, s=HID)
    b.part(name + "a", name, "ell", (0.022, 0.022, 0.014), color, t=[-0.016, 0.012, 0], nt=6, np_=8)
    b.part(name + "b", name, "ell", (0.022, 0.022, 0.014), color, t=[0.016, 0.012, 0], nt=6, np_=8)
    b.part(name + "c", name, "box", (0.03, 0.03, 0.014), color, t=[0, -0.004, 0], r=qz(math.pi / 4))


def sparkle(b, name, parent, color="#ffc94a"):
    b.node(name, parent, s=HID)
    b.part(name + "a", name, "ell", (0.034, 0.008, 0.008), color, nt=5, np_=8)
    b.part(name + "b", name, "ell", (0.008, 0.034, 0.008), color, nt=5, np_=8)


def drop(b, name, parent, color="#5bb8f0"):
    b.node(name, parent, s=HID)
    b.part(name + "m", name, "ell", (0.018, 0.026, 0.014), color, nt=6, np_=8)


def build_props(b):
    for n, p in (("H1", "Root"), ("H2", "Root")):
        heart(b, n, p)
    for n in ("S1", "S2", "S3"):
        sparkle(b, n, "Root", "#ffc94a" if n != "S3" else "#ff9ec0")
    for n, col in (("N1", "#f26b8a"), ("N2", "#3aa0e0")):
        b.node(n, "Root", s=HID)
        b.part(n + "h", n, "ell", (0.03, 0.022, 0.014), col, t=[0, 0, 0], r=qz(0.4), nt=6, np_=10)
        b.part(n + "s", n, "box", (0.008, 0.08, 0.008), col, t=[0.026, 0.04, 0])
        b.part(n + "f", n, "box", (0.03, 0.01, 0.008), col, t=[0.04, 0.078, 0], r=qz(-0.5))
    b.node("Anger", "Head", s=HID, t=[0.17, 0.4, 0.1])
    b.part("Anger1", "Anger", "box", (0.05, 0.012, 0.012), "#e0412f", r=qz(0.78))
    b.part("Anger2", "Anger", "box", (0.05, 0.012, 0.012), "#e0412f", r=qz(-0.78))
    b.part("Anger3", "Anger", "box", (0.012, 0.05, 0.012), "#e0412f")
    for n, x in (("TearL", -0.15), ("TearR", 0.15)):
        drop(b, n, "Head")
        b.nodes[b.byname[n]]["translation"] = [x, 0.14, 0.2]
    drop(b, "Sweat", "Head")
    b.nodes[b.byname["Sweat"]]["translation"] = [0.22, 0.36, 0.1]
    # customer hands (props)
    for n, rot in (("PatHand", qz(0.0)), ("FiveHand", qz(0.0))):
        b.node(n, "Root", s=HID)
        b.part(n + "m", n, "ell", (0.055, 0.05, 0.035), SKIN, nt=8, np_=12)
        b.part(n + "t", n, "ell", (0.02, 0.03, 0.02), SKIN, t=[-0.05, -0.01, 0.0], r=qz(0.6), nt=6, np_=8)
        b.part(n + "s", n, "ell", (0.052, 0.12, 0.05), SLEEVE_PROP, t=[0.09, 0.09, 0], r=qz(-0.8), nt=8, np_=12)


# ------------------------------------------------------------------ animations
def build_anims(b, c):
    flopdir = c["flopdir"]
    EXPR_BASE = {"EyesOpen": True, "MouthSmile": True}
    ALL_EXPR = ["EyesOpen", "EyesStar", "EyesHappy", "EyesCry", "EyesX", "BrowsAngry",
                "MouthSmile", "MouthOpen", "MouthFrown", "MouthWail", "MouthFlat"]
    ONE = [1.0, 1.0, 1.0]

    def vis(on):
        return tuple(ONE if on else HID)

    def switch(name, t0, t1, base):
        """STEP: base state -> flipped between t0..t1 -> base."""
        v0, v1 = vis(base), vis(not base)
        return (name, "scale", [0, t0, t1], [v0, v1, v0], "STEP")

    def appear(name, times, on_flags):
        return (name, "scale", times, [vis(f) for f in on_flags], "STEP")

    def lin(node, path, times, values):
        return (node, path, times, values, "LINEAR")

    def expr(T, on, off=(), t0=0.1, t1=None):
        t1 = (T - 0.15) if t1 is None else t1
        tr = []
        for n in ALL_EXPR:
            if n in on:
                tr.append(switch(n, t0, t1, EXPR_BASE.get(n, False)))
            elif n in off:
                tr.append(switch(n, t0, t1, EXPR_BASE.get(n, False)))
        return tr

    def dur(T):  # anchor animation length
        return lin("Root", "translation", [0, T], [(0, 0, 0), (0, 0, 0)])

    aL, aR = -0.25, 0.25

    # ---------------- Idle
    b.anim("Idle", [
        lin("Upper", "translation", [0, 1, 2], [(0, 0, 0), (0, 0.012, 0), (0, 0, 0)]),
        lin("Head", "rotation", [0, 0.5, 1.5, 2], [qz(0), qz(0.04), qz(-0.04), qz(0)]),
        lin("ArmL", "rotation", [0, 1, 2], [qz(aL), qz(aL - 0.05), qz(aL)]),
        lin("ArmR", "rotation", [0, 1, 2], [qz(aR), qz(aR + 0.05), qz(aR)]),
    ])

    # ---------------- Pat (head pat)
    T = 2.8
    hp = [(0.40, 1.30, 0.06), (0.12, 1.08, 0.09), (0.05, 0.99, 0.09), (0.05, 1.05, 0.09), (0.05, 0.99, 0.09),
          (0.05, 1.05, 0.09), (0.05, 0.99, 0.09), (0.40, 1.30, 0.06)]
    hpt = [0.2, 0.55, 0.85, 1.1, 1.35, 1.6, 1.85, 2.4]
    b.anim("Pat", [dur(T),
                   lin("Upper", "translation", [0, 0.5, 2.3, T], [(0, 0, 0), (0, -0.025, 0), (0, -0.025, 0), (0, 0, 0)]),
                   lin("Head", "rotation", [0, 0.5, 2.3, T], [qz(0), qmul(qz(-0.1), qx(0.18)), qmul(qz(-0.1), qx(0.18)), qz(0)]),
                   lin("ArmL", "rotation", [0, 0.5, 2.3, T], [qz(aL), qz(aL + 0.12), qz(aL + 0.12), qz(aL)]),
                   lin("PatHand", "translation", hpt, hp),
                   appear("PatHand", [0, 0.15, 2.45], [False, True, False]),
                   appear("H1", [0, 0.9, 2.5], [False, True, False]),
                   appear("H2", [0, 1.3, 2.5], [False, True, False]),
                   lin("H1", "translation", [0.9, 2.5], [(-0.2, 0.95, 0.1), (-0.26, 1.15, 0.1)]),
                   lin("H2", "translation", [1.3, 2.5], [(0.26, 0.9, 0.1), (0.32, 1.1, 0.1)]),
                   ] + expr(T, ["EyesHappy"], ["EyesOpen"]))

    # ---------------- HighFive
    T = 2.6
    b.anim("HighFive", [dur(T),
                        lin("ArmR", "rotation", [0, 0.4, 1.1, 1.25, 1.5, 2.0, T],
                            [qz(aR), qz(2.35), qz(2.35), qz(2.45), qz(2.35), qz(2.35), qz(aR)]),
                        lin("ForeR", "rotation", [0, 0.4, T], [qz(0), qz(0.25), qz(0)]),
                        lin("ArmL", "rotation", [0, 0.5, T], [qz(aL), qz(aL - 0.3), qz(aL)]),
                        lin("Head", "rotation", [0, 0.5, 1.9, T], [qz(0), qz(-0.1), qz(-0.1), qz(0)]),
                        lin("Upper", "translation", [0, 1.0, 1.15, 1.35, T],
                            [(0, 0, 0), (0, 0, 0), (0, 0.035, 0), (0, 0, 0), (0, 0, 0)]),
                        lin("FiveHand", "translation", [0.4, 1.1, 1.45, 2.0],
                            [(0.85, 0.66, 0.08), (0.36, 0.64, 0.08), (0.37, 0.64, 0.08), (0.85, 0.7, 0.08)]),
                        lin("FiveHand", "scale", [0, 0.39, 0.4, 1.1, 1.2, 1.45, 2.0, 2.05],
                            [HID, HID, ONE, ONE, (1.2, 1.2, 1.2), ONE, ONE, HID]),
                        appear("S1", [0, 1.1, 1.8], [False, True, False]),
                        appear("S2", [0, 1.15, 1.85], [False, True, False]),
                        lin("S1", "translation", [1.1, 1.8], [(0.38, 0.78, 0.1), (0.42, 0.86, 0.1)]),
                        lin("S2", "translation", [1.15, 1.85], [(0.46, 0.6, 0.1), (0.52, 0.55, 0.1)]),
                        ] + expr(T, ["EyesHappy", "MouthOpen"], ["EyesOpen", "MouthSmile"]))

    # ---------------- Cry (crouch crying)
    T = 3.4
    sob = [0, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, T]
    sobv = [0.0, 0.1, -0.06, 0.07, -0.05, 0.07, -0.05, 0.07, -0.05, 0.07, -0.05, 0.05, 0.0]
    tears = [0.4, 1.0, 1.01, 1.6, 1.61, 2.2, 2.21, 2.8]
    b.anim("Cry", [dur(T),
                   lin("Upper", "translation", [0, 0.5, 2.9, T], [(0, 0, 0), (0, -0.09, 0), (0, -0.09, 0), (0, 0, 0)]),
                   lin("LegL", "scale", [0, 0.5, 2.9, T], [ONE, (1, 0.55, 1), (1, 0.55, 1), ONE]),
                   lin("LegR", "scale", [0, 0.5, 2.9, T], [ONE, (1, 0.55, 1), (1, 0.55, 1), ONE]),
                   lin("Head", "rotation", sob, [qmul(qz(v), qx(0.0 if i in (0, len(sob) - 1) else 0.25)) for i, v in enumerate(sobv)]),
                   lin("ArmL", "rotation", [0, 0.6, 2.8, T], [qz(aL), qz(1.8), qz(1.8), qz(aL)]),
                   lin("ForeL", "rotation", [0, 0.6, 2.8, T], [qz(0), qz(1.3), qz(1.3), qz(0)]),
                   lin("ArmR", "rotation", [0, 0.6, 2.8, T], [qz(aR), qz(-1.8), qz(-1.8), qz(aR)]),
                   lin("ForeR", "rotation", [0, 0.6, 2.8, T], [qz(0), qz(-1.3), qz(-1.3), qz(0)]),
                   appear("TearL", [0, 0.4, 2.9], [False, True, False]),
                   appear("TearR", [0, 0.4, 2.9], [False, True, False]),
                   lin("TearL", "translation", tears, [(-0.15, 0.14, 0.2), (-0.17, 0.0, 0.2)] * 4),
                   lin("TearR", "translation", tears, [(0.15, 0.14, 0.2), (0.17, 0.0, 0.2)] * 4),
                   ] + expr(T, ["EyesCry", "MouthWail"], ["EyesOpen", "MouthSmile"]))

    # ---------------- Sway (happy head swing)
    T = 2.8
    st = [0, 0.35, 0.95, 1.55, 2.15, T]
    b.anim("Sway", [dur(T),
                    lin("Head", "rotation", st, [qz(0), qz(0.3), qz(-0.3), qz(0.3), qz(-0.3), qz(0)]),
                    lin("Upper", "translation", st, [(0, 0, 0), (0.0, 0.02, 0), (0, 0, 0), (0, 0.02, 0), (0, 0, 0), (0, 0, 0)]),
                    lin("ArmL", "rotation", st, [qz(aL), qz(aL - 0.5), qz(aL - 0.1), qz(aL - 0.5), qz(aL - 0.1), qz(aL)]),
                    lin("ArmR", "rotation", st, [qz(aR), qz(aR + 0.1), qz(aR + 0.5), qz(aR + 0.1), qz(aR + 0.5), qz(aR)]),
                    appear("N1", [0, 0.2, 2.5], [False, True, False]),
                    appear("N2", [0, 0.5, 2.6], [False, True, False]),
                    lin("N1", "translation", [0.2, 2.5], [(-0.36, 0.75, 0.05), (-0.42, 1.05, 0.05)]),
                    lin("N2", "translation", [0.5, 2.6], [(0.36, 0.7, 0.05), (0.42, 1.0, 0.05)]),
                    ] + expr(T, ["EyesHappy", "MouthOpen"], ["EyesOpen", "MouthSmile"]))

    # ---------------- Angry (hands on hips)
    T = 3.0
    shake = [0.5, 0.65, 0.8, 0.95, 1.1, 1.25, 1.4, 1.55, 1.7, 1.85, 2.0, 2.15, 2.3]
    sv = [0.03, -0.03] * 6 + [0.03]
    b.anim("Angry", [dur(T),
                     lin("ArmL", "rotation", [0, 0.3, 2.6, T], [qz(aL), qz(-0.9), qz(-0.9), qz(aL)]),
                     lin("ForeL", "rotation", [0, 0.3, 2.6, T], [qz(0), qz(1.7), qz(1.7), qz(0)]),
                     lin("ArmR", "rotation", [0, 0.3, 2.6, T], [qz(aR), qz(0.9), qz(0.9), qz(aR)]),
                     lin("ForeR", "rotation", [0, 0.3, 2.6, T], [qz(0), qz(-1.7), qz(-1.7), qz(0)]),
                     lin("Head", "rotation", [0, 0.3, 2.6, T], [qz(0), qx(0.15), qx(0.15), qz(0)]),
                     lin("Root", "rotation", [0] + shake + [T], [qz(0)] + [qz(v) for v in sv] + [qz(0)]),
                     appear("Anger", [0, 0.3, 0.9, 1.2, 1.8, 2.1, 2.5], [False, True, False, True, False, True, False]),
                     ] + expr(T, ["BrowsAngry", "MouthFrown"], ["MouthSmile"]))

    # ---------------- Think (chin on hands, excited)
    T = 3.2
    b.anim("Think", [dur(T),
                     lin("ArmL", "rotation", [0, 0.5, 2.7, T], [qz(aL), qz(-0.5), qz(-0.5), qz(aL)]),
                     lin("ForeL", "rotation", [0, 0.5, 2.7, T], [qz(0), qz(2.86), qz(2.86), qz(0)]),
                     lin("ArmR", "rotation", [0, 0.5, 2.7, T], [qz(aR), qz(0.5), qz(0.5), qz(aR)]),
                     lin("ForeR", "rotation", [0, 0.5, 2.7, T], [qz(0), qz(-2.86), qz(-2.86), qz(0)]),
                     lin("Head", "rotation", [0, 0.5, 1.2, 1.9, 2.7, T], [qz(0), qz(0.12), qz(0.2), qz(0.08), qz(0.12), qz(0)]),
                     lin("Upper", "translation", [0, 0.8, 1.6, 2.4, T], [(0, 0, 0), (0, 0.02, 0), (0, 0, 0), (0, 0.02, 0), (0, 0, 0)]),
                     appear("S1", [0, 0.5, 1.2, 1.7, 2.4, 2.8], [False, True, False, True, False, False]),
                     appear("S2", [0, 0.8, 1.5, 2.0, 2.7], [False, True, False, True, False]),
                     appear("S3", [0, 1.1, 1.8, 2.3, 2.9], [False, True, False, True, False]),
                     lin("S1", "translation", [0.5, 2.8], [(-0.3, 0.9, 0.1), (-0.34, 1.0, 0.1)]),
                     lin("S2", "translation", [0.8, 2.7], [(0.32, 0.95, 0.1), (0.36, 1.05, 0.1)]),
                     lin("S3", "translation", [1.1, 2.9], [(0.3, 0.7, 0.1), (0.34, 0.78, 0.1)]),
                     ] + expr(T, ["EyesStar"], ["EyesOpen"]))

    # ---------------- Flop (collapsed on the floor)
    T = 3.8
    ang = -flopdir * math.pi / 2  # flopdir -1 = head ends up on the left
    tx = -flopdir * 0.12
    keys = [0, 0.45, 0.7, 3.1, 3.55, T]
    b.anim("Flop", [lin("Root", "rotation", keys, [qz(0), qz(ang * 1.12), qz(ang), qz(ang), qz(0), qz(0)]),
                    lin("Root", "translation", keys,
                        [(0, 0, 0), (tx * 0.6, 0.27, 0.22), (tx, 0.29, 0.22), (tx, 0.29, 0.22), (0, 0, 0), (0, 0, 0)]),
                    lin("ArmL", "rotation", [0, 0.7, 3.1, T], [qz(aL), qz(-1.3), qz(-1.3), qz(aL)]),
                    lin("ArmR", "rotation", [0, 0.7, 3.1, T], [qz(aR), qz(1.3), qz(1.3), qz(aR)]),
                    lin("Head", "rotation", [0, 0.7, 3.1, T], [qz(0), qz(0.18), qz(0.18), qz(0)]),
                    appear("Sweat", [0, 0.8, 3.3], [False, True, False]),
                    lin("Sweat", "translation", [0.8, 3.3], [(0.22, 0.36, 0.1), (0.24, 0.2, 0.1)]),
                    ] + expr(T, ["EyesX", "MouthFlat"], ["EyesOpen", "MouthSmile"], t0=0.3, t1=3.5))

    # ================= clips for the group scene (characters interact with each other) =================
    # Layout assumption: neighbours stand side by side, left -> right = A B C D E.

    # ---------------- Cheer (both arms up, hopping)
    T = 3.0
    hk = [0, 0.4, 0.7, 1.0, 1.3, 1.6, 1.9, 2.2, T]
    hv = [0, 0, 0.08, 0, 0, 0.08, 0, 0, 0]
    b.anim("Cheer", [dur(T),
                     lin("Upper", "translation", hk, [(0, v, 0) for v in hv]),
                     lin("ArmL", "rotation", [0, 0.3, 2.5, T], [qz(aL), qz(-2.2), qz(-2.2), qz(aL)]),
                     lin("ArmR", "rotation", [0, 0.3, 2.5, T], [qz(aR), qz(2.2), qz(2.2), qz(aR)]),
                     lin("ForeL", "rotation", [0, 0.3, 2.5, T], [qz(0), qz(-0.25), qz(-0.25), qz(0)]),
                     lin("ForeR", "rotation", [0, 0.3, 2.5, T], [qz(0), qz(0.25), qz(0.25), qz(0)]),
                     appear("S1", [0, 0.5, 2.4], [False, True, False]),
                     appear("S2", [0, 0.8, 2.5], [False, True, False]),
                     lin("S1", "translation", [0.5, 2.4], [(-0.3, 1.0, 0.1), (-0.34, 1.12, 0.1)]),
                     lin("S2", "translation", [0.8, 2.5], [(0.3, 1.0, 0.1), (0.34, 1.12, 0.1)]),
                     ] + expr(T, ["EyesHappy", "MouthOpen"], ["EyesOpen", "MouthSmile"]))

    # ---------------- FiveR / FiveL (high-five with the neighbour on that side)
    for nm, sx in (("FiveR", 1), ("FiveL", -1)):
        T = 2.6
        arm, fore = ("ArmR", "ForeR") if sx > 0 else ("ArmL", "ForeL")
        other = "ArmL" if sx > 0 else "ArmR"
        base = aR if sx > 0 else aL
        up = 1.9 * sx
        b.anim(nm, [dur(T),
                    lin("Upper", "rotation", [0, 0.4, 2.0, T], [qy(0), qy(0.5 * sx), qy(0.5 * sx), qy(0)]),
                    lin("Head", "rotation", [0, 0.4, 2.0, T], [qy(0), qy(0.2 * sx), qy(0.2 * sx), qy(0)]),
                    lin(arm, "rotation", [0, 0.4, 1.0, 1.15, 1.4, 2.0, T],
                        [qz(base), qz(up), qz(up), qz(up + 0.1 * sx), qz(up), qz(up), qz(base)]),
                    lin(fore, "rotation", [0, 0.4, 2.0, T], [qz(0), qz(0.3 * sx), qz(0.3 * sx), qz(0)]),
                    lin(other, "rotation", [0, 0.5, T], [qz(-base), qz(-base * 1.2), qz(-base)]),
                    appear("S1", [0, 1.1, 1.9], [False, True, False]),
                    lin("S1", "translation", [1.1, 1.9], [(0.27 * sx, 0.62, 0.12), (0.27 * sx, 0.72, 0.12)]),
                    ] + expr(T, ["EyesHappy", "MouthOpen"], ["EyesOpen", "MouthSmile"]))

    # ---------------- PatShoulderR / PatShoulderL (pat the neighbour's shoulder)
    for nm, sx in (("PatShoulderR", 1), ("PatShoulderL", -1)):
        T = 2.6
        arm = "ArmR" if sx > 0 else "ArmL"
        fore = "ForeR" if sx > 0 else "ForeL"
        base = aR if sx > 0 else aL
        tap = [0, 0.5, 0.8, 1.1, 1.4, 1.7, 2.0, T]
        angs = [base, 1.45 * sx, 1.7 * sx, 1.45 * sx, 1.7 * sx, 1.45 * sx, 1.45 * sx, base]
        b.anim(nm, [lin("Root", "translation", [0, 0.5, 2.0, T], [(0, 0, 0), (0.1 * sx, 0, 0), (0.1 * sx, 0, 0), (0, 0, 0)]),
                    lin("Upper", "rotation", [0, 0.5, 2.0, T], [qy(0), qy(0.4 * sx), qy(0.4 * sx), qy(0)]),
                    lin(arm, "rotation", tap, [qz(a) for a in angs]),
                    lin(fore, "rotation", [0, 0.5, 2.0, T], [qz(0), qz(0.15 * sx), qz(0.15 * sx), qz(0)]),
                    appear("H1", [0, 0.9, 2.2], [False, True, False]),
                    lin("H1", "translation", [0.9, 2.2], [(0.42 * sx, 0.7, 0.1), (0.46 * sx, 0.85, 0.1)]),
                    ] + expr(T, ["EyesHappy"], ["EyesOpen"]))

    # ---------------- Shy (gets patted: head down, happy)
    T = 2.6
    b.anim("Shy", [dur(T),
                   lin("Head", "rotation", [0, 0.5, 2.0, T], [qz(0), qmul(qz(0.12), qx(0.2)), qmul(qz(0.12), qx(0.2)), qz(0)]),
                   lin("Upper", "translation", [0, 0.5, 2.0, T], [(0, 0, 0), (0, -0.02, 0), (0, -0.02, 0), (0, 0, 0)]),
                   lin("ArmL", "rotation", [0, 0.5, 2.0, T], [qz(aL), qz(aL + 0.35), qz(aL + 0.35), qz(aL)]),
                   lin("ArmR", "rotation", [0, 0.5, 2.0, T], [qz(aR), qz(aR - 0.35), qz(aR - 0.35), qz(aR)]),
                   appear("H1", [0, 0.6, 2.3], [False, True, False]),
                   appear("H2", [0, 0.9, 2.3], [False, True, False]),
                   lin("H1", "translation", [0.6, 2.3], [(-0.2, 0.98, 0.1), (-0.26, 1.15, 0.1)]),
                   lin("H2", "translation", [0.9, 2.3], [(0.22, 0.95, 0.1), (0.28, 1.12, 0.1)]),
                   ] + expr(T, ["EyesHappy"], ["EyesOpen"]))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    for cid, c in CHARS.items():
        b = build(cid, c)
        n = b.write(os.path.join(out, f"char-{cid}.glb"), "Scaler")
        print(f"char-{cid}.glb  {n / 1024:.0f} KB  clips={[a['name'] for a in b.anims]}")
