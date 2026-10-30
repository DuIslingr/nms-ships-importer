"""Animations: a model's entity file (.ENTITY.MBIN, TkAttachmentData) names its animations (TkAnimationComponentData:
the Idle loop and the Anims list, each a TkAnimationData with a name, a file, Loop / OneShot, a frame range and a speed);
the .ANIM.MBIN (TkAnimMetadata) holds the keyframes: per frame, the rotations (quaternions packed as 3 x u16), scales and
translations of the animated nodes, and one still frame for the nodes that don't move. A node's RotIndex / TransIndex /
ScaleIndex pick its value in a frame's lists when below their length, else in the still frame's (minus that length).
Layouts from libMBIN 7.10.
"""
import math
import struct

from . import mbin

ANIM_LOOP, ANIM_ONESHOT, ANIM_ONESHOT_BLENDABLE, ANIM_CONTROL = 0, 1, 2, 3
ANIM_TYPES = {0: "Loop", 1: "OneShot", 2: "OneShotBlendable", 3: "Control"}
HASH_ANIMATION_COMPONENT = 0x573A9AA9
FPS = 30.0


class TkAnimationData(mbin.Template):
    SIZE = 0x128
    FIELDS = (("anim", 0x50, "fixed", 0x10), ("filename", 0x70, "string", None), ("anim_type", 0xB8, "u32", None),
              ("frame_end", 0xC4, "i32", None), ("frame_end_game", 0xC8, "i32", None), ("frame_start", 0xCC, "i32", None),
              ("priority", 0xD8, "i32", None), ("speed", 0xDC, "f32", None), ("start_node", 0xE0, "fixed", 0x40),
              ("active", 0x120, "u8", None), ("additive", 0x121, "u8", None))


class TkAnimationComponentData(mbin.Template):
    SIZE = 0x1A0
    FIELDS = (("idle", 0x000, "inline", TkAnimationData), ("anim_group", 0x128, "fixed", 0x10),
              ("anims", 0x148, "list", TkAnimationData))


class TkAnimNodeData(mbin.Template):
    SIZE = 0x20
    FIELDS = (("node", 0x00, "string", None), ("rot_index", 0x10, "i32", None), ("scale_index", 0x14, "i32", None),
              ("trans_index", 0x18, "i32", None))


def read_frame(r, o):
    """A TkAnimNodeFrameData at o: rotations (list of (x, y, z, w)), scales and translations (lists of (x, y, z))."""
    base, n = r.header16(o)
    rotations = []
    for i in range(n // 3):
        cx, cy, cz = struct.unpack_from("<HHH", r.b, base + 6 * i)
        rotations.append(unpack_quaternion(cx, cy, cz))
    base, n = r.header16(o + 0x10)
    scales = [tuple(r.floats(base + 16 * i, 3)) for i in range(n)]
    base, n = r.header16(o + 0x20)
    translations = [tuple(r.floats(base + 16 * i, 3)) for i in range(n)]
    return {"rotations": rotations, "scales": scales, "translations": translations}


def unpack_quaternion(cx, cy, cz):
    """libMBIN's packed quaternion: three 15-bit components around 0x3FFF scaled by 1 / (0x3FFF sqrt 2), the top bits
    of the first two saying which component was dropped (3 x, 2 y, 1 z, 0 w) and rebuilt as positive."""
    scale = 1.0 / (0x3FFF * math.sqrt(2.0))
    drop = ((cy >> 15) | ((cx >> 14) & 2))
    qx = scale * ((cx & 0x7FFF) - 0x3FFF)
    qy = scale * ((cy & 0x7FFF) - 0x3FFF)
    qz = scale * (cz - 0x3FFF)
    qw = math.sqrt(max(min(1.0 - qx * qx - qy * qy - qz * qz, 1.0), 0.0))
    if drop == 3:      # x dropped: the stored three are (w, x, y)? libMBIN: new Quaternion(qw, qx, qy, qz, ...) for case 3
        return (qw, qx, qy, qz)
    if drop == 2:
        return (qx, qw, qy, qz)
    if drop == 1:
        return (qx, qy, qw, qz)
    return (qx, qy, qz, qw)


class Animation:
    """A decoded .ANIM.MBIN: `nodes` (names in order), `frames`, and `track(node)` -> per frame (rotation, scale,
    translation), each None when the node keeps its still value."""

    def __init__(self, data):
        _, h = mbin.header(data), None
        r = mbin.Reader(data)
        o = mbin.HEADER
        self.still = read_frame(r, o)
        base, n = r.header16(o + 0x30)
        self.frames = [read_frame(r, base + 0x30 * i) for i in range(n)]
        base, n = r.header16(o + 0x40)
        self.node_data = [TkAnimNodeData.read(r, base + 0x20 * i) for i in range(n)]
        self.frame_count = r.i32(o + 0x50)
        self.node_count = r.i32(o + 0x54)
        self.nodes = [nd["node"] for nd in self.node_data]

    def _value(self, kind, index, frame):
        animated = self.frames[frame][kind] if self.frames else []
        if index < len(animated):
            return animated[index], True
        still = self.still[kind]
        j = index - len(animated)
        return (still[j] if 0 <= j < len(still) else None), False

    def track(self, node):
        """[(rotation xyzw, scale xyz, translation xyz)] per frame for the node, or None when it isn't in the file;
        `animated(node)` says which of the three change."""
        nd = next((d for d in self.node_data if d["node"].lower() == node.lower()), None)
        if nd is None:
            return None
        out = []
        for f in range(len(self.frames)):
            rot, _ = self._value("rotations", nd["rot_index"], f)
            sc, _ = self._value("scales", nd["scale_index"], f)
            tr, _ = self._value("translations", nd["trans_index"], f)
            out.append((rot, sc, tr))
        return out

    def animated(self, node):
        nd = next((d for d in self.node_data if d["node"].lower() == node.lower()), None)
        if nd is None or not self.frames:
            return (False, False, False)
        f0 = self.frames[0]
        return (nd["rot_index"] < len(f0["rotations"]), nd["scale_index"] < len(f0["scales"]), nd["trans_index"] < len(f0["translations"]))

    def still_pose(self, node):
        nd = next((d for d in self.node_data if d["node"].lower() == node.lower()), None)
        if nd is None:
            return None
        return (self._value("rotations", nd["rot_index"], 0)[0], self._value("scales", nd["scale_index"], 0)[0],
                self._value("translations", nd["trans_index"], 0)[0])


def entity_animations(data):
    """The TkAnimationComponentData of an entity file (TkAttachmentData) as {idle, anims: [...]}, or None."""
    r = mbin.Reader(data)
    h = mbin.header(data)
    if h["name_hash"] != 0x6874FF60:
        raise mbin.MBINError("not a TkAttachmentData")
    base, n = r.header16(mbin.HEADER + 0x10)
    for i in range(n):
        e = base + 0x20 * i
        off, name_hash, magic = struct.unpack_from("<qII", r.b, e)
        if magic != 0xEEEEEE01:
            continue
        if name_hash == HASH_ANIMATION_COMPONENT and off:
            return TkAnimationComponentData.read(r, e + off)
    return None


def entity_path(scene_path):
    """The entity file a scene's ATTACHMENT attribute names is read by the caller; this is the usual place of a model's
    own entity: <folder>/<model>/entities/<model>.entity.mbin."""
    base = scene_path[: -len(".scene.mbin")]
    folder, name = base.rsplit("/", 1)
    return f"{folder}/{name}/entities/{name}.entity.mbin"


# --- entity components beyond the animations ---------------------------------------------------------------------

HASH_ROTATION_COMPONENT = 0x8EB35CA7
HASH_ATTACHMENT = 0x6874FF60


class TkRotationComponentData(mbin.Template):
    """A part that turns forever about an axis of its own frame: `speed` in turns per second (0.1 the usual spinner,
    0.5 the fighters' engine turbines; negative the other way)."""
    SIZE = 0x1C
    FIELDS = (("axis", 0x00, "floats", 3), ("speed", 0x10, "f32", None), ("sync_group", 0x14, "i32", None),
              ("always_update", 0x18, "u8", None), ("use_model_node", 0x19, "u8", None))


def entity_components(data):
    """{name hash: decoded component} of an entity file, for the components this module knows (animation, rotation)."""
    r = mbin.Reader(data)
    h = mbin.header(data)
    if h["name_hash"] != HASH_ATTACHMENT:
        raise mbin.MBINError("not a TkAttachmentData")
    out = {}
    base, n = r.header16(mbin.HEADER + 0x10)
    for i in range(n):
        e = base + 0x20 * i
        off, name_hash, magic = struct.unpack_from("<qII", r.b, e)
        if magic != 0xEEEEEE01 or not off:
            continue
        if name_hash == HASH_ANIMATION_COMPONENT:
            out[name_hash] = TkAnimationComponentData.read(r, e + off)
        elif name_hash == HASH_ROTATION_COMPONENT:
            out[name_hash] = TkRotationComponentData.read(r, e + off)
    return out


# --- what to play ---------------------------------------------------------------------------------------------------

import re as _re

NOT_IN_FLIGHT = _re.compile(r"(gear|land|enter|exit|eject|hatch|scanline|takeoff|blank)", _re.I)


def flight_loop(component):
    """The animation a flying ship plays all the time: the first Loop among the idle and the list whose name and file
    say nothing of landing gear, landing, entering or leaving; None when there is none."""
    for a in [component["idle"]] + list(component["anims"]):
        if a["anim_type"] != ANIM_LOOP or not a["filename"]:
            continue
        if NOT_IN_FLIGHT.search(a["anim"] or "") or NOT_IN_FLIGHT.search(a["filename"].rsplit("/", 1)[-1]):
            continue
        return a
    return None


def transition(component, name):
    """The one-shot animation called `name` (TAKEOFF, LANDING), or None."""
    for a in [component["idle"]] + list(component["anims"]):
        if (a["anim"] or "").upper() == name.upper() and a["filename"]:
            return a
    return None


def local_matrix(rotation, scale, translation):
    """A node's local 4x4 from an animation's quaternion (x, y, z, w), scale and translation (None keeps 1 / 0)."""
    import numpy as np
    x, y, z, w = rotation if rotation else (0.0, 0.0, 0.0, 1.0)
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.identity(4)
    M[:3, :3] = R @ np.diag(scale if scale else (1.0, 1.0, 1.0))
    M[:3, 3] = translation if translation else (0.0, 0.0, 0.0)
    return M
