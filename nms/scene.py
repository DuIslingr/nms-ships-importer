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
import re

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
    """A mesh (or locator / light / reference / attachment) placed in the assembled model's frame. `chain` is every
    node from the walk's root down to this one (scene roots included), so a world matrix can be built again with
    some nodes' transforms replaced (an animation's pose: `world`)."""
    __slots__ = ("node", "matrix", "scene", "path", "chain")

    def __init__(self, node, matrix, scene, path, chain=()):
        self.node, self.matrix, self.scene, self.path, self.chain = node, matrix, scene, path, chain

    def world(self, overrides=None):
        """The world matrix from the chain; `overrides` maps a node to the local matrix to use instead of its own."""
        M = np.identity(4)
        for n in self.chain:
            if overrides and n in overrides:
                M = M @ overrides[n]
            elif n is not n.scene.root:
                M = M @ n.local
        return M

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
    and `references` collect what the walk found; COLLISION nodes are skipped. Every LOD's meshes are collected (the
    iOS game keeps LOD1 as the finest of its big hulls): `finest_meshes()` picks the finest with a stream per mesh.
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
        self.attachments = []   # nodes with an ATTACHMENT (entity file) attribute
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
        self._walk(s.root, np.identity(4) if matrix is None else matrix, s, depth, trail or s.root.name, ())
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
        trail = s.root.name + "/" + "/".join(x.name for x in reversed(chain[:-1])) if len(chain) > 1 else s.root.name
        self._walk(node, M, s, 0, trail, (s.root,) + tuple(reversed(chain[1:])))
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

    def _walk(self, node, parent_matrix, scene, depth, trail, chain):
        if node.type == "COLLISION":
            return
        if node is not scene.root and not self.choose(node):
            return
        own = self._chooser(scene)
        if own is not None and node is not scene.root and not own(node):
            return
        M = parent_matrix @ node.local if node is not scene.root else parent_matrix
        path = trail + "/" + node.name if node is not scene.root else trail
        chain = chain + (node,)
        placed = Placed(node, M, scene, path, chain)
        if node.attrs.get("ATTACHMENT"):
            self.attachments.append(placed)
        if node.type == "MESH":
            self.meshes.append(placed)
        elif node.type == "LOCATOR" or node.type == "JOINT":
            self.locators.append(placed)
        elif node.type == "LIGHT":
            self.lights.append(placed)
        elif node.type == "REFERENCE":
            ref = node.scenegraph
            self.references.append(placed)
            if ref and depth < self.max_depth:
                if self.banks.exists(ref):
                    sub = self.scene(ref)
                    self._walk(sub.root, M, sub, depth + 1, path, chain)
                else:
                    self.missing.append(ref)
            # a REFERENCE node's own children (a procedural model's nested options sit under their parent's reference)
        for c in node.children:
            self._walk(c, M, scene, depth, path, chain)


LOD_SUFFIX = re.compile(r"lod\d+", re.I)


def finest_meshes(meshes, floor=0, drop_detail=False):
    """Of the placed meshes, those of the finest LOD level that has a stream, per mesh family (`BodyLOD0`, `BodyLOD1`
    and their `SUB1Body...` children are families of their own): the iOS game ships no LOD0 for its big hulls. With a
    `floor`, the finest level at or above it that the family has (else its finest), for the big ships' budgets; with
    `drop_detail`, a family with no level but its finest is left out altogether (a station's interior props and the
    derelicts' gore have no LODs: the game never sees them from afar)."""
    levels = {}
    for p in meshes:
        if not p.scene.geometry.has(p.node.name):
            continue
        levels.setdefault(LOD_SUFFIX.sub("", p.path).lower(), set()).add(p.node.lod)
    best = {}
    for key, lods in levels.items():
        above = [l for l in lods if l >= floor]
        if drop_detail and len(lods) < 2:
            best[key] = None
            continue
        best[key] = min(above) if above else max(lods)
    return [p for p in meshes if p.scene.geometry.has(p.node.name) and best.get(LOD_SUFFIX.sub("", p.path).lower()) == p.node.lod]


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
