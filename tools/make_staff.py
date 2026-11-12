#!/usr/bin/env python3
"""Build an ORIGINAL test character ("Staff") as a binary glTF (.glb) with three
animation clips: Idle, Wave, Jump. Pure stdlib + struct, no 3D software needed.

Conventions: Y up, front faces +Z, feet at y=0, total height ~1.0 unit.
Animations are node TRS animations (no skinning) so the file stays tiny.

Usage: python3 make_character.py <out.glb>
"""
import json
import math
import struct
import sys

out = sys.argv[1] if len(sys.argv) > 1 else "staff.glb"

# ---------------------------------------------------------------- geometry
def box(sx, sy, sz, cx=0.0, cy=0.0, cz=0.0):
    """Return (positions, normals, indices) for an axis-aligned box."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    faces = [  # normal, 4 corner offsets (CCW seen from outside)
        ((0, 0, 1), [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]),
        ((0, 0, -1), [(hx, -hy, -hz), (-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz)]),
        ((1, 0, 0), [(hx, -hy, hz), (hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz)]),
        ((-1, 0, 0), [(-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz)]),
        ((0, 1, 0), [(-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz), (-hx, hy, -hz)]),
        ((0, -1, 0), [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)]),
    ]
    pos, nor, idx = [], [], []
    for n, corners in faces:
        base = len(pos)
        for (x, y, z) in corners:
            pos.append((x + cx, y + cy, z + cz))
            nor.append(n)
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    return pos, nor, idx


def quat_z(theta):
    return (0.0, 0.0, math.sin(theta / 2), math.cos(theta / 2))


# ---------------------------------------------------------------- scene graph
MATERIALS = {
    "skin": (0.99, 0.87, 0.74, 1.0),
    "shirt": (0.25, 0.60, 0.85, 1.0),
    "apron": (0.96, 0.62, 0.22, 1.0),
    "cap": (0.88, 0.25, 0.25, 1.0),
    "ink": (0.12, 0.12, 0.16, 1.0),
    "badge": (1.00, 0.85, 0.20, 1.0),
    "blush": (0.98, 0.60, 0.60, 1.0),
    "pants": (0.22, 0.25, 0.40, 1.0),
}
mat_names = list(MATERIALS)

# name -> dict(parent, translation, mesh=(box args, material))
PARTS = [
    ("Root", None, (0, 0, 0), None),
    ("Body", "Root", (0, 0, 0), ((0.34, 0.30, 0.22, 0, 0.33, 0), "shirt")),
    ("Apron", "Root", (0, 0.30, 0.115), ((0.30, 0.24, 0.02, 0, 0, 0), "apron")),
    ("Badge", "Root", (0.08, 0.42, 0.13), ((0.07, 0.045, 0.02, 0, 0, 0), "badge")),
    ("Head", "Root", (0, 0.48, 0), ((0.42, 0.38, 0.38, 0, 0.19, 0), "skin")),
    ("Cap", "Head", (0, 0.36, 0), ((0.46, 0.09, 0.42, 0, 0.045, 0), "cap")),
    ("Brim", "Head", (0, 0.37, 0.22), ((0.28, 0.03, 0.14, 0, 0, 0.04), "cap")),
    ("EyeL", "Head", (-0.10, 0.22, 0.19), ((0.07, 0.09, 0.02, 0, 0, 0.01), "ink")),
    ("EyeR", "Head", (0.10, 0.22, 0.19), ((0.07, 0.09, 0.02, 0, 0, 0.01), "ink")),
    ("CheekL", "Head", (-0.16, 0.14, 0.19), ((0.07, 0.04, 0.02, 0, 0, 0.01), "blush")),
    ("CheekR", "Head", (0.16, 0.14, 0.19), ((0.07, 0.04, 0.02, 0, 0, 0.01), "blush")),
    ("Mouth", "Head", (0, 0.12, 0.19), ((0.08, 0.025, 0.02, 0, 0, 0.01), "ink")),
    ("ArmL", "Root", (-0.22, 0.45, 0), ((0.10, 0.25, 0.10, 0, -0.115, 0), "shirt")),
    ("ArmR", "Root", (0.22, 0.45, 0), ((0.10, 0.25, 0.10, 0, -0.115, 0), "shirt")),
    ("LegL", "Root", (-0.08, 0.18, 0), ((0.12, 0.18, 0.12, 0, -0.09, 0), "pants")),
    ("LegR", "Root", (0.08, 0.18, 0), ((0.12, 0.18, 0.12, 0, -0.09, 0), "pants")),
]
node_index = {name: i for i, (name, *_rest) in enumerate(PARTS)}

# ---------------------------------------------------------------- binary buffer
bin_data = bytearray()
buffer_views, accessors = [], []


def add_view(data: bytes, target=None):
    while len(bin_data) % 4:
        bin_data.append(0)
    view = {"buffer": 0, "byteOffset": len(bin_data), "byteLength": len(data)}
    if target:
        view["target"] = target
    bin_data.extend(data)
    buffer_views.append(view)
    return len(buffer_views) - 1


def add_accessor(view, comp, count, typ, mn=None, mx=None):
    acc = {"bufferView": view, "componentType": comp, "count": count, "type": typ}
    if mn is not None:
        acc["min"], acc["max"] = mn, mx
    accessors.append(acc)
    return len(accessors) - 1


FLOAT, USHORT = 5126, 5123
meshes, nodes = [], []
for name, parent, trans, mesh_def in PARTS:
    node = {"name": name, "translation": list(trans)}
    if mesh_def:
        args, mat = mesh_def
        pos, nor, idx = box(*args)
        pv = add_view(b"".join(struct.pack("<3f", *p) for p in pos), 34962)
        nv = add_view(b"".join(struct.pack("<3f", *n) for n in nor), 34962)
        iv = add_view(b"".join(struct.pack("<H", i) for i in idx), 34963)
        xs, ys, zs = zip(*pos)
        pa = add_accessor(pv, FLOAT, len(pos), "VEC3", [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)])
        na = add_accessor(nv, FLOAT, len(nor), "VEC3")
        ia = add_accessor(iv, USHORT, len(idx), "SCALAR")
        meshes.append({"name": name + "Mesh", "primitives": [{
            "attributes": {"POSITION": pa, "NORMAL": na}, "indices": ia,
            "material": mat_names.index(mat)}]})
        node["mesh"] = len(meshes) - 1
    nodes.append(node)
for name, parent, *_ in PARTS:
    if parent:
        nodes[node_index[parent]].setdefault("children", []).append(node_index[name])

# ---------------------------------------------------------------- animations
animations = []


def make_anim(name, tracks):
    """tracks: list of (node_name, path, times, values)."""
    samplers, channels = [], []
    for node_name, path, times, values in tracks:
        tv = add_view(b"".join(struct.pack("<f", t) for t in times))
        ta = add_accessor(tv, FLOAT, len(times), "SCALAR", [min(times)], [max(times)])
        flat = [c for v in values for c in v]
        ov = add_view(b"".join(struct.pack("<f", c) for c in flat))
        typ = {"translation": "VEC3", "rotation": "VEC4", "scale": "VEC3"}[path]
        oa = add_accessor(ov, FLOAT, len(values), typ)
        samplers.append({"input": ta, "output": oa, "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1,
                         "target": {"node": node_index[node_name], "path": path}})
    animations.append({"name": name, "samplers": samplers, "channels": channels})


def bob(y):
    return (0.0, y, 0.0)


# Idle: 2 s seamless loop (first == last key)
make_anim("Idle", [
    ("Root", "translation", [0, 1, 2], [bob(0), bob(0.015), bob(0)]),
    ("Head", "rotation", [0, 0.5, 1.5, 2], [quat_z(0), quat_z(0.06), quat_z(-0.06), quat_z(0)]),
    ("ArmL", "rotation", [0, 1, 2], [quat_z(-0.08), quat_z(-0.14), quat_z(-0.08)]),
    ("ArmR", "rotation", [0, 1, 2], [quat_z(0.08), quat_z(0.14), quat_z(0.08)]),
])

# Wave: right arm up and swing, ends at rest pose
make_anim("Wave", [
    ("ArmR", "rotation", [0, 0.3, 0.55, 0.8, 1.05, 1.3, 1.6],
     [quat_z(0.08), quat_z(2.4), quat_z(1.9), quat_z(2.6), quat_z(1.9), quat_z(2.6), quat_z(0.08)]),
    ("Head", "rotation", [0, 0.3, 1.3, 1.6], [quat_z(0), quat_z(-0.08), quat_z(-0.08), quat_z(0)]),
])

# Jump: crouch, launch, land; both arms swing up
make_anim("Jump", [
    ("Root", "translation", [0, 0.15, 0.5, 0.85, 1.0],
     [bob(0), bob(-0.04), bob(0.30), bob(0), bob(0)]),
    ("Root", "scale", [0, 0.15, 0.5, 0.85, 1.0],
     [(1, 1, 1), (1.08, 0.9, 1.08), (0.95, 1.06, 0.95), (1.08, 0.9, 1.08), (1, 1, 1)]),
    ("ArmL", "rotation", [0, 0.15, 0.5, 0.85, 1.0],
     [quat_z(-0.08), quat_z(-0.08), quat_z(-2.6), quat_z(-0.4), quat_z(-0.08)]),
    ("ArmR", "rotation", [0, 0.15, 0.5, 0.85, 1.0],
     [quat_z(0.08), quat_z(0.08), quat_z(2.6), quat_z(0.4), quat_z(0.08)]),
])

# ---------------------------------------------------------------- assemble glb
gltf = {
    "asset": {"version": "2.0", "generator": "store-ar-platform/tools/make_character.py"},
    "scene": 0,
    "scenes": [{"name": "Scene", "nodes": [node_index["Root"]]}],
    "nodes": nodes,
    "meshes": meshes,
    "materials": [{"name": n, "pbrMetallicRoughness": {
        "baseColorFactor": list(MATERIALS[n]), "metallicFactor": 0.0, "roughnessFactor": 0.8}}
        for n in mat_names],
    "animations": animations,
    "accessors": accessors,
    "bufferViews": buffer_views,
    "buffers": [{"byteLength": len(bin_data)}],
}
js = json.dumps(gltf, separators=(",", ":")).encode()
js += b" " * (-len(js) % 4)
while len(bin_data) % 4:
    bin_data.append(0)
total = 12 + 8 + len(js) + 8 + len(bin_data)
with open(out, "wb") as f:
    f.write(struct.pack("<III", 0x46546C67, 2, total))
    f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
    f.write(struct.pack("<II", len(bin_data), 0x004E4942) + bytes(bin_data))
print(f"wrote {out} ({total} bytes, animations: {[a['name'] for a in animations]})")
