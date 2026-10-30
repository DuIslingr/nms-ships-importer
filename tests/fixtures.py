"""Synthetic game files for the tests: HGPAK archives and MBIN scenes, descriptors, geometry and materials written with
the same layouts the readers expect. Nothing here comes from the game."""
import hashlib
import math
import os
import struct
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from nms import mbin  # noqa: E402


def write(path, data):
    with open(path, "wb") as f:
        f.write(data)


# --- HGPAK ----------------------------------------------------------------------------------------------------------

def make_hgpak(files, codec="zstd", chunk_size=0x10000, raw_chunks=(), tail_padding=0):
    """An HGPAK v2 archive holding `files` ({name: bytes}) in that order. codec: 'zstd', None (stored); `raw_chunks`
    are chunk indices stored uncompressed although the archive is compressed; `tail_padding` bytes follow the last
    file inside the decompressed data (the game's archives run past their last entry)."""
    names = list(files)
    manifest = "\r\n".join(names).encode()
    entries = [manifest] + [files[n] for n in names]
    offsets, data = [], bytearray()
    for e in entries:
        offsets.append(len(data))
        data += e
        data += b"\0" * ((-len(data)) % 16)
    data += b"\0" * tail_padding
    compressed = codec is not None
    header_size = 0x30 + 32 * len(entries)
    if compressed:
        chunks = [bytes(data[i:i + chunk_size]) for i in range(0, len(data), chunk_size)]
        header_size += 8 * len(chunks)
    data_offset = (header_size + 15) & ~15
    out = bytearray()
    out += b"HGPAK\0\0\0" + struct.pack("<QQQ?7xQ", 2, len(entries), len(chunks) if compressed else 0, compressed, data_offset)
    for name, e, off in zip(["manifest"] + names, entries, offsets):
        key = hashlib.md5(name.lower().encode()).digest() if name != "manifest" else b"\0" * 16
        out += struct.pack("<16sQQ", key, data_offset + off, len(e))
    body = bytearray()
    if compressed:
        from compression import zstd
        stored = []
        for i, c in enumerate(chunks):
            z = c if i in raw_chunks else zstd.compress(c)
            if len(z) >= len(c):
                z = c
            stored.append(z)
            body += z + b"\0" * ((-len(z)) % 16)
        out += struct.pack("<%dQ" % len(stored), *[len(z) for z in stored])
    else:
        body = data
    out += b"\0" * (data_offset - len(out))
    out += body
    return bytes(out)


# --- MBIN -------------------------------------------------------------------------------------------------------------

class MbinWriter:
    def __init__(self, name_hash, guid=0x1234, magic=mbin.MAGIC_MBIN):
        self.buf = bytearray(0x20)
        struct.pack_into("<QHHIQQ", self.buf, 0, magic, 3300, 4, name_hash, guid, 0)

    def alloc(self, size, align=8):
        self.buf += b"\0" * ((-len(self.buf)) % align)
        off = len(self.buf)
        self.buf += b"\0" * size
        return off

    def put(self, off, fmt, *vals):
        struct.pack_into(fmt, self.buf, off, *vals)

    def fixed(self, off, text, size):
        data = text.encode()[: size - 1]
        self.buf[off:off + len(data)] = data

    def header(self, at, target, count, magic=0xAAAAAA01):
        self.put(at, "<qiI", target - at if count else 0, count, magic)

    def string(self, at, text):
        data = text.encode() + b"\0"
        off = self.alloc(len(data), 1)
        self.buf[off:off + len(data)] = data
        self.header(at, off, len(data) - 1)

    def strings(self, at, texts):
        base = self.alloc(16 * len(texts))
        self.header(at, base, len(texts))
        for i, t in enumerate(texts):
            self.string(base + 16 * i, t)

    def ints(self, at, values):
        base = self.alloc(4 * len(values))
        self.header(at, base, len(values))
        for i, v in enumerate(values):
            self.put(base + 4 * i, "<i", v)

    def vec4s(self, at, values):
        base = self.alloc(16 * len(values))
        self.header(at, base, len(values))
        for i, v in enumerate(values):
            self.put(base + 16 * i, "<4f", *v)

    def bytes_list(self, at, data):
        off = self.alloc(len(data), 16)
        self.buf[off:off + len(data)] = data
        self.header(at, off, len(data))

    def done(self):
        return bytes(self.buf)


def scene_node(w, at, node):
    """node = {"name", "type", "attrs": {k: v}, "transform": (rot3, scale3, trans3), "children": [...]}"""
    attrs = list(node.get("attrs", {}).items())
    base = w.alloc(0x20 * len(attrs))
    w.header(at, base, len(attrs))
    for i, (k, v) in enumerate(attrs):
        w.fixed(base + 0x20 * i, k, 0x10)
        w.string(base + 0x20 * i + 0x10, v)
    children = node.get("children", [])
    cbase = w.alloc(0x80 * len(children))
    w.header(at + 0x10, cbase, len(children))
    w.header(at + 0x20, 0, 0)
    w.string(at + 0x30, node["name"])
    w.fixed(at + 0x40, node["type"], 0x10)
    rot, scale, trans = node.get("transform", ((0, 0, 0), (1, 1, 1), (0, 0, 0)))
    w.put(at + 0x50, "<9f", *rot, *scale, *trans)
    w.put(at + 0x74, "<I", abs(hash(node["name"])) & 0xFFFFFFFF)
    for i, c in enumerate(children):
        scene_node(w, cbase + 0x80 * i, c)


def make_scene(root):
    w = MbinWriter(0x3DB87E47)
    at = w.alloc(0x80)
    scene_node(w, at, root)
    return w.done()


def descriptor_list(w, at, groups):
    """groups = [{"type": "_WINGS_", "options": [{"id", "name", "chance", "refs": [...], "groups": [...]}]}]"""
    gbase = w.alloc(0x20 * len(groups))
    w.header(at, gbase, len(groups))
    for gi, g in enumerate(groups):
        ga = gbase + 0x20 * gi
        opts = g["options"]
        obase = w.alloc(0xC8 * len(opts))
        w.header(ga, obase, len(opts))
        w.fixed(ga + 0x10, g["type"], 0x10)
        for oi, o in enumerate(opts):
            oa = obase + 0xC8 * oi
            w.fixed(oa, o["id"], 0x20)
            nested = o.get("groups", [])
            if nested:
                ebase = w.alloc(16)
                w.header(oa + 0x20, ebase, 1)
                child = w.alloc(0x10)
                w.put(ebase, "<qII", child - ebase, 0x4026294F, 0xEEEEEE01)
                descriptor_list(w, child, nested)
            else:
                w.header(oa + 0x20, 0, 0)
            w.strings(oa + 0x30, o.get("refs", []))
            w.put(oa + 0x40, "<f", o.get("chance", 1.0))
            w.fixed(oa + 0x44, o.get("name", o["id"]), 0x80)


def make_descriptor(groups):
    w = MbinWriter(0x4026294F)
    at = w.alloc(0x10)
    descriptor_list(w, at, groups)
    return w.done()


def octa_encode(n):
    """A unit normal as the packed u32 the 7.x vertex stream holds."""
    x, y, z = n / np.abs(n).sum()
    if z < 0:
        x, y = (1 - abs(y)) * (1 if x >= 0 else -1), (1 - abs(x)) * (1 if y >= 0 else -1)
    f0 = int(round((x + 1) / 2 * 1023))
    f1 = int(round((y + 1) / 2 * 1023))
    return f0 | (f1 << 10)


def make_geometry(meshes):
    """meshes = {id: (positions (n,3), uvs (n,2), normals (n,3), indices (m,3))}: the geometry and data MBINs."""
    g = MbinWriter(0x819C3220, magic=mbin.MAGIC_GEOMETRY)
    at = g.alloc(0x160)
    # position layout: POSITION half4 at 0, UV half4 at 8; vertex layout: COLOUR ubyte4 at 0, packed u32 at 4
    for base, elements, stride in ((at, [(5131, 0, 0, 4), (5131, 8, 1, 4)], 16), (at + 0x20, [(5121, 0, 4, 4), (5125, 4, 11, 1)], 8)):
        eb = g.alloc(0x0C * len(elements))
        g.header(base, eb, len(elements))
        for i, (typ, off, sem, size) in enumerate(elements):
            g.put(eb + 0x0C * i, "<IiBBBB", 0, typ, 0, off, sem, size)
        g.put(base + 0x18, "<ii", len(elements), stride)
    for off in (0x40, 0x60, 0xE0, 0xF0, 0x100, 0x120):
        g.ints(at + off, [])
    for off in (0x50, 0xC0, 0xD0):
        g.vec4s(at + off, [])
    g.strings(at + 0x110, [])
    mb = g.alloc(0x38 * len(meshes))
    g.header(at + 0x140, mb, len(meshes))
    d = MbinWriter(0x40025754, magic=mbin.MAGIC_GEOMETRY)
    dat = d.alloc(0x10)
    sb = d.alloc(0x48 * len(meshes))
    d.header(dat, sb, len(meshes))
    total_idx = 0
    for i, (mid, (pos, uv, nrm, idx)) in enumerate(meshes.items()):
        n = len(pos)
        p = np.zeros((n, 8), np.float16)
        p[:, :3] = pos
        p[:, 3] = 1
        p[:, 4:6] = uv
        pblob = p.tobytes()
        v = np.zeros((n, 2), np.uint32)
        v[:, 0] = 0xFFFFFFFF
        v[:, 1] = [octa_encode(np.asarray(x, np.float64)) for x in nrm]
        vblob = v.tobytes()
        iblob = np.asarray(idx, np.uint16).tobytes()
        g.string(mb + 0x38 * i, mid)
        g.put(mb + 0x38 * i + 0x18, "<6i", len(vblob), len(iblob), 0, len(vblob), 0, len(pblob))
        d.string(sb + 0x48 * i, mid)
        d.bytes_list(sb + 0x48 * i + 0x10, vblob + iblob)
        d.bytes_list(sb + 0x48 * i + 0x20, pblob)
        d.put(sb + 0x48 * i + 0x38, "<3i", len(iblob), len(vblob), len(pblob))
        total_idx += len(idx) * 3
    g.put(at + 0x150, "<4i", 0, total_idx, 1, sum(len(m[0]) for m in meshes.values()))
    return g.done(), d.done()


def make_material(name, material_class=45, diffuse=None, masks=None, normal=None, colour=(1, 1, 1, 1), flags=(0,)):
    w = MbinWriter(0x4737D48A)
    at = w.alloc(0xA8)
    w.ints(at, list(flags))
    w.ints(at + 0x10, [])
    w.string(at + 0x20, "")
    w.string(at + 0x30, "")
    w.string(at + 0x40, name)
    samplers = [(n, m) for n, m in (("gDiffuseMap", diffuse), ("gMasksMap", masks), ("gNormalMap", normal)) if m]
    sb = w.alloc(0x50 * len(samplers))
    w.header(at + 0x50, sb, len(samplers))
    for i, (n, m) in enumerate(samplers):
        w.string(sb + 0x50 * i + 0x20, m)
        w.string(sb + 0x50 * i + 0x30, n)
    w.string(at + 0x60, "SHADERS/UBERSHADER.SHADER.BIN")
    ub = w.alloc(0x30)
    w.header(at + 0x70, ub, 1)
    w.put(ub, "<4f", *colour)
    w.string(ub + 0x20, "gMaterialColourVec4")
    w.header(at + 0x80, 0, 0)
    w.put(at + 0x9D, "<B", material_class)
    return w.done()


def make_dds_dxt1(width=8, height=8, rgb=(255, 128, 0)):
    """A DDS with one DXT1 block colour (every block the same)."""
    r, g, b = rgb
    c565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    block = struct.pack("<HHI", c565, c565, 0)
    header = bytearray(128)
    header[:4] = b"DDS "
    struct.pack_into("<IIIIII", header, 4, 124, 0x1007, height, width, max(1, width * height // 2), 0)
    struct.pack_into("<I", header, 28, 1)
    struct.pack_into("<II4s", header, 76, 32, 0x4, b"DXT1")
    struct.pack_into("<I", header, 108, 0x1000)
    return bytes(header) + block * ((width // 4) * (height // 4))


# --- animations and entities ----------------------------------------------------------------------------------------

def pack_quaternion(q):
    """libMBIN's packed quaternion (3 x u16) for (x, y, z, w) with w >= 0: w is the dropped component."""
    x, y, z, w = q
    if w < 0:
        x, y, z, w = -x, -y, -z, -w
    scale = 0x3FFF * math.sqrt(2.0)
    cx = int(round(x * scale)) + 0x3FFF
    cy = int(round(y * scale)) + 0x3FFF
    cz = int(round(z * scale)) + 0x3FFF
    # drop code 0 (w): top bits of cx (bit 15) and cy (bit 15) both clear
    return struct.pack("<HHH", cx & 0x7FFF, cy & 0x7FFF, cz & 0xFFFF)


def make_animation(nodes, frames, still):
    """An .ANIM.MBIN: nodes = [(name, rot_index, scale_index, trans_index)]; frames = [{"rotations": [...], "scales":
    [...], "translations": [...]}] (quaternions xyzw, vec3s); still = the same for the still frame."""
    w = MbinWriter(0x8E7F1986)
    at = w.alloc(0x60)

    def frame(o, f):
        rots = f.get("rotations", [])
        data = b"".join(pack_quaternion(q) for q in rots)
        off = w.alloc(len(data) or 1, 2)
        w.buf[off:off + len(data)] = data
        w.header(o, off, 3 * len(rots))
        w.vec4s(o + 0x10, [tuple(v) + (1.0,) for v in f.get("scales", [])])
        w.vec4s(o + 0x20, [tuple(v) + (1.0,) for v in f.get("translations", [])])
    frame(at, still)
    fb = w.alloc(0x30 * len(frames))
    w.header(at + 0x30, fb, len(frames))
    for i, f in enumerate(frames):
        frame(fb + 0x30 * i, f)
    nb = w.alloc(0x20 * len(nodes))
    w.header(at + 0x40, nb, len(nodes))
    for i, (name, ri, si, ti) in enumerate(nodes):
        w.string(nb + 0x20 * i, name)
        w.put(nb + 0x20 * i + 0x10, "<iii", ri, si, ti)
    w.put(at + 0x50, "<ii", len(frames), len(nodes))
    return w.done()


def make_entity(anims=None, rotation=None):
    """A .ENTITY.MBIN (TkAttachmentData) with an animation component (anims = [(name, filename, type)], the first the
    idle) and / or a rotation component (axis, speed)."""
    w = MbinWriter(0x6874FF60)
    at = w.alloc(0x40)
    w.header(at, 0, 0)
    comps = [c for c in (("anim", anims), ("rot", rotation)) if c[1]]
    cb = w.alloc(0x20 * len(comps))
    w.header(at + 0x10, cb, len(comps))
    for i, (kind, value) in enumerate(comps):
        e = cb + 0x20 * i
        if kind == "rot":
            t = w.alloc(0x20)
            w.put(e, "<qII", t - e, 0x8EB35CA7, 0xEEEEEE01)
            axis, speed = value
            w.put(t, "<4f", *axis, 1.0)
            w.put(t + 0x10, "<fiBB", speed, -1, 1, 0)
        else:
            t = w.alloc(0x1A0)
            w.put(e, "<qII", t - e, 0x573A9AA9, 0xEEEEEE01)

            def anim_data(o, a):
                name, filename, typ = a
                w.fixed(o + 0x50, name, 0x10)
                w.string(o + 0x70, filename)
                w.put(o + 0xB8, "<I", typ)
                w.put(o + 0xDC, "<f", 1.0)
                w.put(o + 0x120, "<B", 1)
                for off in (0x20, 0x30, 0x60, 0x80, 0x90):
                    w.header(o + off, 0, 0)
            anim_data(t, value[0])
            rest = value[1:]
            w.header(t + 0x138, 0, 0)
            ab = w.alloc(0x128 * len(rest))
            w.header(t + 0x148, ab, len(rest))
            for j, a in enumerate(rest):
                anim_data(ab + 0x128 * j, a)
            for off in (0x158, 0x168, 0x178, 0x188):
                w.header(t + off, 0, 0)
    return w.done()
