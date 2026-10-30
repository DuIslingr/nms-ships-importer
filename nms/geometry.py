"""A model's meshes from its .GEOMETRY.MBIN.<PC|IOS> and .GEOMETRY.DATA.MBIN.<PC|IOS> (7.x layout, the same bytes on
both platforms).

The geometry file holds the two vertex layouts and, per mesh id (a MESH node's name, upper case), the sizes of its
streams; the data file holds the streams themselves: `mesh_stream` = the vertex stream (vertex_size bytes) followed by
the index data (index_size bytes, u16 or u32 by `indices_16bit`), `position_stream` = the position stream.

The 7.x layouts (every ship part checked):
    position stream, stride 16: POSITION half4 (w = 1) at 0, TEXCOORD half4 (u, v, u2, v2) at 8
    vertex stream, stride 8:    COLOUR ubyte4 at 0; a packed u32 at 4 (semantic 11): the normal as an octahedral pair
                                of 10-bit unsigned fields in bits 0-9 / 10-19 (checked against the face normals of several
                                meshes: 0.98-0.99 agreement); bits 20-31 the tangent (not decoded here).
Older layouts (NORMAL / TANGENT as separate elements, float or half positions) are decoded by their elements too.
"""
import math
import struct

import numpy as np

from . import mbin

GL_BYTE, GL_UNSIGNED_BYTE, GL_SHORT, GL_UNSIGNED_SHORT, GL_UNSIGNED_INT, GL_FLOAT, GL_HALF = 5120, 5121, 5122, 5123, 5125, 5126, 5131
SEM_POSITION, SEM_UV, SEM_NORMAL, SEM_TANGENT, SEM_COLOUR, SEM_PACKED = 0, 1, 2, 3, 4, 11
DTYPES = {GL_BYTE: "i1", GL_UNSIGNED_BYTE: "u1", GL_SHORT: "<i2", GL_UNSIGNED_SHORT: "<u2", GL_UNSIGNED_INT: "<u4",
          GL_FLOAT: "<f4", GL_HALF: "<f2"}
NORMALISED = {GL_BYTE: 127.0, GL_UNSIGNED_BYTE: 255.0, GL_SHORT: 32767.0, GL_UNSIGNED_SHORT: 65535.0}


class Mesh:
    """One drawable: positions (n, 3) float32, uvs (n, 2), normals (n, 3) or None, colours (n, 4) uint8 or None,
    indices (m, 3) uint32, all in the model's own frame."""
    __slots__ = ("id", "positions", "uvs", "uvs2", "normals", "colours", "indices")

    def __init__(self, id, positions, uvs, uvs2, normals, colours, indices):
        self.id, self.positions, self.uvs, self.uvs2, self.normals, self.colours, self.indices = id, positions, uvs, uvs2, normals, colours, indices

    @property
    def triangle_count(self):
        return len(self.indices)


def octahedral(x, y):
    """Unit vectors from octahedral coordinates in -1..1 (the lower hemisphere folded)."""
    z = 1.0 - np.abs(x) - np.abs(y)
    t = np.clip(-z, 0.0, 1.0)
    x = x + np.where(x >= 0, -t, t)
    y = y + np.where(y >= 0, -t, t)
    v = np.stack([x, y, z], axis=1)
    return v / np.maximum(np.linalg.norm(v, axis=1), 1e-9)[:, None]


def unpack_normals(words):
    """Normals from the packed u32 of the 7.x vertex stream."""
    f0 = (words & 0x3FF).astype(np.float32) / 1023.0 * 2.0 - 1.0
    f1 = ((words >> 10) & 0x3FF).astype(np.float32) / 1023.0 * 2.0 - 1.0
    return octahedral(f0, f1)


def _element(stream, stride, count, el):
    """An element's values as (count, size) float32 (or uint8 for an un-normalised byte colour)."""
    dtype = np.dtype(DTYPES[el["type"]])
    size = el["size"]
    view = np.ndarray((count, size), dtype=dtype, buffer=stream, offset=el["offset"], strides=(stride, dtype.itemsize))
    if el["type"] in (GL_FLOAT, GL_HALF):
        return view.astype(np.float32)
    if el["semantic"] == SEM_COLOUR and el["type"] == GL_UNSIGNED_BYTE:
        return np.ascontiguousarray(view)
    if el["type"] == GL_UNSIGNED_INT:
        return np.ascontiguousarray(view)
    scale = NORMALISED[el["type"]]
    return view.astype(np.float32) / scale


class Geometry:
    """The meshes of one model: `mesh(id)` decodes a MESH node's streams (ids are compared upper case)."""

    def __init__(self, geometry_bytes, data_bytes):
        _, self.info = mbin.load(geometry_bytes, "TkGeometryData")
        _, streams = mbin.load(data_bytes, "TkGeometryStreamData")
        self.data = data_bytes
        self.streams = {s["id"].upper(): s for s in streams["streams"]}
        self.indices_16bit = bool(self.info["indices_16bit"])
        self.position_layout = self.info["position_layout"]
        self.vertex_layout = self.info["vertex_layout"]

    @property
    def mesh_ids(self):
        return list(self.streams)

    def has(self, id):
        return id.upper() in self.streams

    def _indices(self, blob, vsz, isz, count):
        """The mesh's triangles. The header's Indices16Bit says u16 or u32, but some models (the solar ships' proc
        geometry) say u32 and store u16, so the width that fits the vertex count wins."""
        def read(width):
            arr = np.frombuffer(blob, dtype="<u2" if width == 2 else "<u4", count=isz // width, offset=vsz)
            return arr[: len(arr) - len(arr) % 3].reshape(-1, 3).astype(np.uint32)
        order = (2, 4) if self.indices_16bit else (4, 2)
        for width in order:
            if isz % width:
                continue
            idx = read(width)
            if not len(idx) or idx.max() < count:
                return idx
        return read(order[0])

    def mesh(self, id):
        s = self.streams.get(id.upper())
        if s is None:
            raise KeyError(id)
        mo, mn = s["mesh_stream"]
        po, pn = s["position_stream"]
        vsz, isz, psz = s["vertex_size"], s["index_size"], s["position_size"]
        blob = self.data[mo:mo + mn]
        pblob = self.data[po:po + pn]
        if len(blob) < vsz + isz or len(pblob) < psz:
            raise mbin.MBINError(f"mesh {id}: the data file is shorter than its streams say")
        pstride = self.position_layout["stride"] or 16
        vstride = self.vertex_layout["stride"] or 8
        count = psz // pstride if pstride else 0
        indices = self._indices(blob, vsz, isz, count)
        positions = uvs = uvs2 = normals = colours = None
        for el in self.position_layout["elements"]:
            vals = _element(pblob, pstride, count, el)
            if el["semantic"] == SEM_POSITION:
                positions = np.ascontiguousarray(vals[:, :3])
            elif el["semantic"] == SEM_UV:
                uvs = np.ascontiguousarray(vals[:, :2])
                if vals.shape[1] >= 4:
                    uvs2 = np.ascontiguousarray(vals[:, 2:4])
            elif el["semantic"] == SEM_NORMAL:
                normals = np.ascontiguousarray(vals[:, :3])
        vcount = vsz // vstride if vstride else 0
        vblob = blob[:vsz]
        for el in self.vertex_layout["elements"]:
            if vcount != count or el["offset"] + el["size"] > vstride:
                continue
            vals = _element(vblob, vstride, vcount, el)
            if el["semantic"] == SEM_COLOUR:
                colours = vals if vals.dtype == np.uint8 else (np.clip(vals, 0, 1) * 255).astype(np.uint8)
            elif el["semantic"] in (5, 6):
                continue   # blend indices / weights of a skinned part: not used
            elif el["semantic"] == SEM_PACKED and el["type"] == GL_UNSIGNED_INT:
                normals = unpack_normals(vals[:, 0].astype(np.uint32))
            elif el["semantic"] == SEM_NORMAL:
                normals = np.ascontiguousarray(vals[:, :3])
            elif el["semantic"] == SEM_POSITION and positions is None:
                positions = np.ascontiguousarray(vals[:, :3])
            elif el["semantic"] == SEM_UV and uvs is None:
                uvs = np.ascontiguousarray(vals[:, :2])
        if positions is None:
            raise mbin.MBINError(f"mesh {id}: no positions in the vertex layouts")
        if len(indices) and indices.max() >= len(positions):
            raise mbin.MBINError(f"mesh {id}: an index points past its {len(positions)} vertices")
        if uvs is None:
            uvs = np.zeros((len(positions), 2), np.float32)
        if normals is None:
            normals = face_normals(positions, indices)
        return Mesh(id, positions, uvs, uvs2, normals, colours, indices)


def face_normals(positions, indices):
    """Smooth vertex normals from the faces, for a layout without any."""
    n = np.zeros_like(positions)
    if len(indices):
        a, b, c = positions[indices[:, 0]], positions[indices[:, 1]], positions[indices[:, 2]]
        fn = np.cross(b - a, c - a)
        for k in range(3):
            np.add.at(n, indices[:, k], fn)
    ln = np.linalg.norm(n, axis=1)
    n[ln > 0] /= ln[ln > 0][:, None]
    n[ln == 0] = (0, 1, 0)
    return n.astype(np.float32)


def transform_matrix(t):
    """A TkTransformData (degrees) as a 4x4 matrix: the rotations apply Z first, then X, then Y (M = Ry Rx Rz; checked
    against the joint bind poses of 322 rotated joints of the ship parts, the only order that matches them all)."""
    rx, ry, rz = (math.radians(v) for v in t["rot"])
    sx, sy, sz = t["scale"]
    cx, sxn, cy, syn, cz, szn = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sxn], [0, sxn, cx]])
    Ry = np.array([[cy, 0, syn], [0, 1, 0], [-syn, 0, cy]])
    Rz = np.array([[cz, -szn, 0], [szn, cz, 0], [0, 0, 1]])
    R = Ry @ Rx @ Rz
    M = np.identity(4)
    M[:3, :3] = R @ np.diag([sx, sy, sz])
    M[:3, 3] = t["trans"]
    return M


def apply(M, points):
    """Points (n, 3) through a 4x4 matrix."""
    p = np.hstack([points, np.ones((len(points), 1), points.dtype)])
    return (p @ M.T)[:, :3].astype(np.float32)


def apply_normals(M, normals):
    """Directions through the matrix's rotation (its scale removed)."""
    R = M[:3, :3]
    n = normals @ np.linalg.inv(R).T
    ln = np.linalg.norm(n, axis=1)
    n[ln > 0] /= ln[ln > 0][:, None]
    return n.astype(np.float32)
