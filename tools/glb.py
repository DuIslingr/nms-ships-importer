"""A small glTF 2.0 binary (.glb) writer: nodes in a hierarchy (TRS), a mesh per node, PBR materials by name, no
textures embedded (the mod's shipkits.json `materials` put the maps on the materials by name), and animations
(linear samplers on node rotation / translation / scale)."""
import json
import math
import struct

import numpy as np


def quaternion_from_matrix(R):
    """(x, y, z, w) of a rotation matrix (3x3, orthonormal)."""
    m = R
    t = m[0, 0] + m[1, 1] + m[2, 2]
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        return (float((m[2, 1] - m[1, 2]) / s), float((m[0, 2] - m[2, 0]) / s), float((m[1, 0] - m[0, 1]) / s), float(0.25 * s))
    if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        return (float(0.25 * s), float((m[0, 1] + m[1, 0]) / s), float((m[0, 2] + m[2, 0]) / s), float((m[2, 1] - m[1, 2]) / s))
    if m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        return (float((m[0, 1] + m[1, 0]) / s), float(0.25 * s), float((m[1, 2] + m[2, 1]) / s), float((m[0, 2] - m[2, 0]) / s))
    s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
    return (float((m[0, 2] + m[2, 0]) / s), float((m[1, 2] + m[2, 1]) / s), float(0.25 * s), float((m[1, 0] - m[0, 1]) / s))


def quaternion_multiply(a, b):
    """a * b for (x, y, z, w) quaternions: b's rotation first, then a's."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def axis_angle(axis, angle):
    ax = np.asarray(axis, np.float64)
    n = np.linalg.norm(ax)
    if n < 1e-9:
        return (0.0, 0.0, 0.0, 1.0)
    ax = ax / n
    s = math.sin(angle / 2)
    return (float(ax[0] * s), float(ax[1] * s), float(ax[2] * s), float(math.cos(angle / 2)))


def trs(M):
    """(translation, rotation xyzw, scale) of a 4x4 without shear."""
    M = np.asarray(M, np.float64)
    t = M[:3, 3]
    scale = np.linalg.norm(M[:3, :3], axis=0)
    scale = np.where(scale < 1e-12, 1.0, scale)
    R = M[:3, :3] / scale
    if np.linalg.det(R) < 0:
        R[:, 0] *= -1
        scale = scale.copy()
        scale[0] *= -1
    return [float(x) for x in t], quaternion_from_matrix(R), [float(x) for x in scale]


class Writer:
    def __init__(self):
        self.buffers = []
        self.length = 0
        self.views = []
        self.accessors = []
        self.meshes = []
        self.nodes = []
        self.materials = []
        self.material_index = {}
        self.animations = []

    def _blob(self, arr, target=None):
        data = np.ascontiguousarray(arr).tobytes()
        pad = (-len(data)) % 4
        self.buffers.append(data + b"\0" * pad)
        view = {"buffer": 0, "byteOffset": self.length, "byteLength": len(data)}
        if target:
            view["target"] = target
        self.length += len(data) + pad
        self.views.append(view)
        return len(self.views) - 1

    def accessor(self, arr, component, kind, target=None, minmax=False):
        idx = self._blob(arr, target)
        acc = {"bufferView": idx, "componentType": component, "count": int(arr.shape[0]), "type": kind}
        if minmax:
            acc["min"] = [float(x) for x in (arr.min(0) if arr.ndim > 1 else [arr.min()])]
            acc["max"] = [float(x) for x in (arr.max(0) if arr.ndim > 1 else [arr.max()])]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def material(self, name, base_color=(1, 1, 1, 1), metallic=0.0, roughness=0.7, emissive=None, alpha_mode=None,
                 double_sided=False, extras=None):
        if name in self.material_index:
            return self.material_index[name]
        m = {"name": name, "pbrMetallicRoughness": {"baseColorFactor": [float(x) for x in base_color],
                                                   "metallicFactor": float(metallic), "roughnessFactor": float(roughness)}}
        if emissive:
            m["emissiveFactor"] = [float(x) for x in emissive[:3]]
        if alpha_mode:
            m["alphaMode"] = alpha_mode
        if double_sided:
            m["doubleSided"] = True
        if extras:
            m["extras"] = extras
        self.materials.append(m)
        self.material_index[name] = len(self.materials) - 1
        return self.material_index[name]

    def add_node(self, name, parent=None, translation=None, rotation=None, scale=None, extras=None):
        """An empty node; `parent` is another node's index (None: a root of the scene)."""
        node = {"name": name}
        if translation is not None and any(abs(v) > 1e-9 for v in translation):
            node["translation"] = [float(x) for x in translation]
        if rotation is not None and (abs(rotation[3] - 1) > 1e-9 or any(abs(v) > 1e-9 for v in rotation[:3])):
            node["rotation"] = [float(x) for x in rotation]
        if scale is not None and any(abs(v - 1) > 1e-9 for v in scale):
            node["scale"] = [float(x) for x in scale]
        if extras:
            node["extras"] = extras
        self.nodes.append(node)
        idx = len(self.nodes) - 1
        if parent is not None:
            self.nodes[parent].setdefault("children", []).append(idx)
        return idx

    def add_mesh(self, name, positions, normals, uvs, indices, material, colours=None, uvs2=None, extras=None,
                 parent=None, translation=None, rotation=None, scale=None):
        """Positions / normals (n, 3) float32, uvs (n, 2), indices (m, 3), on a node named `name`."""
        positions = np.asarray(positions, np.float32)
        attrs = {"POSITION": self.accessor(positions, 5126, "VEC3", 34962, minmax=True)}
        if normals is not None:
            attrs["NORMAL"] = self.accessor(np.asarray(normals, np.float32), 5126, "VEC3", 34962)
        if uvs is not None:
            attrs["TEXCOORD_0"] = self.accessor(np.asarray(uvs, np.float32), 5126, "VEC2", 34962)
        if uvs2 is not None:
            attrs["TEXCOORD_1"] = self.accessor(np.asarray(uvs2, np.float32), 5126, "VEC2", 34962)
        if colours is not None:
            attrs["COLOR_0"] = self.accessor(np.asarray(colours, np.uint8), 5121, "VEC4", 34962)
            self.accessors[-1]["normalized"] = True
        idx = np.asarray(indices, np.uint32).reshape(-1)
        if idx.size and idx.max() < 65536:
            idx_acc = self.accessor(idx.astype(np.uint16), 5123, "SCALAR", 34963)
        else:
            idx_acc = self.accessor(idx, 5125, "SCALAR", 34963)
        prim = {"attributes": attrs, "indices": idx_acc, "material": material}
        self.meshes.append({"name": name, "primitives": [prim]})
        node = self.add_node(name, parent, translation, rotation, scale, extras)
        self.nodes[node]["mesh"] = len(self.meshes) - 1
        return node

    def add_empty(self, name, translation=None, extras=None):
        return self.add_node(name, None, translation, None, None, extras)

    def add_animation(self, name, channels):
        """channels: [(node index, "rotation" | "translation" | "scale", times (k,), values (k, 4 | 3))]."""
        anim = {"name": name, "samplers": [], "channels": []}
        for node, path, times, values in channels:
            times = np.asarray(times, np.float32)
            values = np.asarray(values, np.float32)
            if len(times) < 2:
                continue
            t_acc = self.accessor(times, 5126, "SCALAR", minmax=True)
            v_acc = self.accessor(values, 5126, "VEC4" if path == "rotation" else "VEC3")
            anim["samplers"].append({"input": t_acc, "output": v_acc, "interpolation": "LINEAR"})
            anim["channels"].append({"sampler": len(anim["samplers"]) - 1, "target": {"node": node, "path": path}})
        if anim["channels"]:
            self.animations.append(anim)
            return len(self.animations) - 1
        return None

    def document(self, extras=None):
        roots = [i for i, n in enumerate(self.nodes) if not any(i in p.get("children", ()) for p in self.nodes)]
        doc = {"asset": {"version": "2.0", "generator": "nms_ships_importer"},
               "scene": 0, "scenes": [{"nodes": roots}],
               "nodes": self.nodes, "meshes": self.meshes, "materials": self.materials,
               "accessors": self.accessors, "bufferViews": self.views, "buffers": [{"byteLength": self.length}]}
        if not self.materials:
            del doc["materials"]
        if self.animations:
            doc["animations"] = self.animations
        if extras:
            doc["extras"] = extras
        return doc

    def save(self, path, extras=None):
        doc = json.dumps(self.document(extras), separators=(",", ":")).encode("utf-8")
        doc += b" " * ((-len(doc)) % 4)
        binary = b"".join(self.buffers)
        total = 12 + 8 + len(doc) + 8 + len(binary)
        with open(path, "wb") as f:
            f.write(struct.pack("<4sII", b"glTF", 2, total))
            f.write(struct.pack("<II", len(doc), 0x4E4F534A))
            f.write(doc)
            f.write(struct.pack("<II", len(binary), 0x004E4942))
            f.write(binary)
        return total


def read(path):
    """(json, binary chunk) of a .glb, for the tests."""
    with open(path, "rb") as f:
        magic, version, total = struct.unpack("<4sII", f.read(12))
        assert magic == b"glTF"
        ln, kind = struct.unpack("<II", f.read(8))
        doc = json.loads(f.read(ln))
        rest = f.read()
    binary = b""
    if rest:
        ln, kind = struct.unpack_from("<II", rest, 0)
        binary = rest[8:8 + ln]
    return doc, binary
