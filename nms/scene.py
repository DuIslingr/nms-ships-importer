"""Scene files (.SCENE.MBIN) as trees, resolved through their REFERENCE nodes, with the meshes, materials and locators
of a model in one frame.

A scene's root is a MODEL node (its GEOMETRY attribute names the geometry files without their suffix); under it MESH
nodes (attributes BATCHSTART / BATCHCOUNT, VERTRSTART / VERTREND, LODLEVEL, MATERIAL = the material file without
.MBIN, MESHLINK), LOCATOR, JOINT, LIGHT, COLLISION and REFERENCE nodes (SCENEGRAPH = another scene to put here). A
procedural model keeps its options as REFERENCE nodes named like the descriptor's entries (`_Cockpit_D`); which of them
show is the descriptor's choice (descriptors.py), so this module only walks what it is told to.
"""
import os
import posixpath

import numpy as np

from . import geometry, mbin


class Node:
    __slots__ = ("name", "type", "attrs", "transform", "children", "parent", "scene")

    def __init__(self, raw, parent=None, scene=None):
        self.name = raw["name"]
        self.type = raw["type"]
        self.attrs = mbin.attributes(raw)
        self.transform = raw["transform"]
        self.parent = parent
        self.scene = scene
        self.children = [Node(c, self, scene) for c in raw["children"]]

    @property
    def local(self):
        return geometry.transform_matrix(self.transform)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def find(self, name):
        name = name.lower()
        for n in self.walk():
            if n.name.lower() == name:
                return n
        return None

    @property
    def scenegraph(self):
        """A REFERENCE node's scene path (game path, lower case, with .scene.mbin)."""
        return game_path(self.attrs.get("SCENEGRAPH", ""))

    @property
    def lod(self):
        try:
            return int(self.attrs.get("LODLEVEL", "0"))
        except ValueError:
            return 0

    def __repr__(self):
        return f"{self.type} {self.name}"


def game_path(p):
    """A path as the game writes it (back-slashes, upper case) as the archives spell it."""
    return p.replace("\\", "/").lower()


class Scene:
    """One scene file: its root node, its geometry (loaded on demand) and the folder its materials live in."""

    def __init__(self, banks, path):
        self.banks = banks
        self.path = game_path(path)
        _, raw = mbin.load(banks.read(self.path), "TkSceneNodeData")
        self.root = Node(raw, None, self)
        self._geometry = None

    @property
    def geometry_base(self):
        base = self.root.attrs.get("GEOMETRY")
        if base:
            base = game_path(base)
            if base.endswith(".geometry.mbin"):
                base = base[: -len(".geometry.mbin")]
            return base
        return self.path[: -len(".scene.mbin")]

    @property
    def geometry(self):
        if self._geometry is None:
            suffix = self.banks.geometry_suffix
            base = self.geometry_base
            try:
                g = self.banks.read(f"{base}.geometry.mbin.{suffix}")
                d = self.banks.read(f"{base}.geometry.data.mbin.{suffix}")
            except KeyError:
                other = "pc" if suffix == "ios" else "ios"
                g = self.banks.read(f"{base}.geometry.mbin.{other}")
                d = self.banks.read(f"{base}.geometry.data.mbin.{other}")
            self._geometry = geometry.Geometry(g, d)
        return self._geometry

    def material_path(self, node):
        """The material file of a MESH node (game path), or None."""
        m = node.attrs.get("MATERIAL")
        if not m:
            return None
        m = game_path(m)
        if not m.endswith(".mbin"):
            m += ".mbin"
        return m


class Placed:
    """A mesh (or locator / light / reference) placed in the assembled model's frame."""
    __slots__ = ("node", "matrix", "scene", "path")

    def __init__(self, node, matrix, scene, path):
        self.node, self.matrix, self.scene, self.path = node, matrix, scene, path

    @property
    def position(self):
        return self.matrix[:3, 3]

    @property
    def forward(self):
        return self.matrix[:3, :3] @ np.array([0.0, 0.0, 1.0])


class Assembler:
    """Walks a scene and the scenes it references, with a chooser deciding which optional nodes show.

    `choose(node)` returns False to leave a node (and its subtree) out: the descriptor's unpicked options. A REFERENCE
    node's scene is loaded through `banks` (cached) and put at the node's world matrix. `meshes`, `locators`, `lights`
    and `references` collect what the walk found; LODLEVEL above 0 and COLLISION nodes are skipped.
    """

    def __init__(self, banks, choose=None, max_depth=12, pick=None):
        self.banks = banks
        self.choose = choose or (lambda node: True)
        self.pick = pick
        self.max_depth = max_depth
        self.scenes = {}
        self.choosers = {}
        self.meshes = []
        self.locators = []
        self.lights = []
        self.references = []
        self.missing = []

    def scene(self, path):
        path = game_path(path)
        s = self.scenes.get(path)
        if s is None:
            s = self.scenes[path] = Scene(self.banks, path)
        return s

    def assemble(self, path, matrix=None, depth=0, trail=""):
        s = self.scene(path)
        self.choosers.setdefault(s.path, None)   # the root scene's options are `choose`'s call, not its own descriptor's
        self._walk(s.root, np.identity(4) if matrix is None else matrix, s, depth, trail or s.root.name)
        return self

    def assemble_node(self, path, name, matrix=None, within=None):
        """Walks only the subtree of the node called `name` of the scene at `path` (inside the node `within` when
        given: a nested option's node), placed where the scene puts it."""
        s = self.scene(path)
        self.choosers.setdefault(s.path, None)
        parent = s.root.find(within) if within else s.root
        if parent is None:
            raise KeyError(f"{path}: no node {within}")
        node = parent.find(name)
        if node is None:
            raise KeyError(f"{path}: no node {name}" + (f" under {within}" if within else ""))
        M = np.identity(4) if matrix is None else matrix
        chain, n = [], node
        while n is not None and n is not s.root:
            chain.append(n)
            n = n.parent
        for n in reversed(chain[1:]):
            M = M @ n.local
        self._walk(node, M, s, 0, s.root.name + "/" + "/".join(x.name for x in reversed(chain[:-1])) if len(chain) > 1 else s.root.name)
        return self

    def _chooser(self, scene):
        """The scene's own descriptor's choice of its sub-options (a part's optional details), through `pick`."""
        if scene.path in self.choosers:
            return self.choosers[scene.path]
        chooser = None
        if self.pick is not None:
            dpath = scene.path[: -len(".scene.mbin")] + ".descriptor.mbin"
            if self.banks.exists(dpath):
                chooser = self.pick(scene.path, self.banks.read(dpath))
        self.choosers[scene.path] = chooser
        return chooser

    def _walk(self, node, parent_matrix, scene, depth, trail):
        if node.type == "COLLISION":
            return
        if node.type == "MESH" and node.lod > 0:
            return
        if node is not scene.root and not self.choose(node):
            return
        own = self._chooser(scene)
        if own is not None and node is not scene.root and not own(node):
            return
        M = parent_matrix @ node.local if node is not scene.root else parent_matrix
        path = trail + "/" + node.name if node is not scene.root else trail
        if node.type == "MESH":
            self.meshes.append(Placed(node, M, scene, path))
        elif node.type == "LOCATOR" or node.type == "JOINT":
            self.locators.append(Placed(node, M, scene, path))
        elif node.type == "LIGHT":
            self.lights.append(Placed(node, M, scene, path))
        elif node.type == "REFERENCE":
            ref = node.scenegraph
            self.references.append(Placed(node, M, scene, path))
            if ref and depth < self.max_depth:
                if self.banks.exists(ref):
                    sub = self.scene(ref)
                    self._walk(sub.root, M, sub, depth + 1, path)
                else:
                    self.missing.append(ref)
            # a REFERENCE node's own children (a procedural model's nested options sit under their parent's reference)
        for c in node.children:
            self._walk(c, M, scene, depth, path)


def material_of(banks, placed, cache):
    """The decoded TkMaterialData of a placed mesh (cached by path), or None when it has none."""
    p = placed.scene.material_path(placed.node)
    if not p:
        return None, None
    if p in cache:
        return p, cache[p]
    try:
        _, m = mbin.load(banks.read(p), "TkMaterialData")
    except (KeyError, mbin.MBINError):
        m = None
    cache[p] = m
    return p, m
