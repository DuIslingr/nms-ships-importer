"""A small glTF 2.0 binary (.glb) writer: one scene, a node per mesh, PBR materials by name, no textures embedded (the
mod's shipkits.json `materials` put the maps on the materials by name)."""
import json
import struct

import numpy as np


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
            acc["min"] = [float(x) for x in arr.min(0)]
            acc["max"] = [float(x) for x in arr.max(0)]
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

    def add_mesh(self, name, positions, normals, uvs, indices, material, colours=None, uvs2=None, extras=None):
        """Positions / normals (n, 3) float32, uvs (n, 2), indices (m, 3), one node named `name`."""
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
        node = {"name": name, "mesh": len(self.meshes) - 1}
        if extras:
            node["extras"] = extras
        self.nodes.append(node)
        return len(self.nodes) - 1

    def add_empty(self, name, translation=None, extras=None):
        node = {"name": name}
        if translation is not None:
            node["translation"] = [float(x) for x in translation]
        if extras:
            node["extras"] = extras
        self.nodes.append(node)
        return len(self.nodes) - 1

    def document(self, extras=None):
        doc = {"asset": {"version": "2.0", "generator": "nms_ships_importer"},
               "scene": 0, "scenes": [{"nodes": list(range(len(self.nodes)))}],
               "nodes": self.nodes, "meshes": self.meshes, "materials": self.materials,
               "accessors": self.accessors, "bufferViews": self.views, "buffers": [{"byteLength": self.length}]}
        if not self.materials:
            del doc["materials"]
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
