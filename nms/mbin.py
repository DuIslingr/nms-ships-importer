"""MBIN files (No Man's Sky's compiled data templates), decoded with the layouts of the few templates the ships use.

A file is a 0x20-byte header then the root template at 0x20:

    0x00 u64 magic   CC.. (MBIN) or DD.. (the geometry's .MBIN.PC / .MBIN.IOS)
    0x08 u16 MBIN version (3300 in 7.x)      0x0A u16 compiler header version
    0x0C u32 name hash of the root template  0x10 u64 template GUID   0x18 u64 timestamp

Fields are laid out at fixed offsets (libMBIN's declaration order with natural alignment); the dynamic ones are
headers of 16 bytes that point elsewhere in the file, relative to the header's own position:

    list            i64 offset, i32 count, u32 magic (low byte 1; AAAAAA01, the geometry's FEFEFE01)
    string (VariableSizeString / GcFilename)   i64 offset, i32 length, u32 magic
    generic list    the same header; at offset, count x { i64 offset (from the entry), u32 name hash, u32 EEEEEE01 }

The PC and the iOS builds of the same game version write byte-identical MBINs (checked on 7.10: the scenes, descriptors,
materials and geometry headers), so one decoder serves both; only the vertex streams' file suffix differs.
Layouts from libMBIN 7.10 (monkeyman192/MBINCompiler): TkSceneNodeData, TkSceneNodeAttributeData, TkTransformData,
TkModelDescriptorList, TkResourceDescriptorList, TkResourceDescriptorData, TkGeometryData, TkVertexLayout,
TkVertexElement, TkMeshMetaData, TkGeometryStreamData, TkMeshData, TkMaterialData, TkMaterialSampler,
TkMaterialUniform_Float.
"""
import struct

HEADER = 0x20
MAGIC_MBIN = 0xCCCCCCCCCCCCCCCC
MAGIC_GEOMETRY = 0xDDDDDDDDDDDDDDDD


class MBINError(Exception):
    pass


class Reader:
    __slots__ = ("b",)

    def __init__(self, data):
        self.b = data

    def u8(self, o): return self.b[o]
    def i8(self, o): return struct.unpack_from("<b", self.b, o)[0]
    def u16(self, o): return struct.unpack_from("<H", self.b, o)[0]
    def i32(self, o): return struct.unpack_from("<i", self.b, o)[0]
    def u32(self, o): return struct.unpack_from("<I", self.b, o)[0]
    def i64(self, o): return struct.unpack_from("<q", self.b, o)[0]
    def u64(self, o): return struct.unpack_from("<Q", self.b, o)[0]
    def f32(self, o): return struct.unpack_from("<f", self.b, o)[0]

    def floats(self, o, n):
        return list(struct.unpack_from("<%df" % n, self.b, o))

    def fixed(self, o, n):
        """A fixed-size string field."""
        return self.b[o:o + n].split(b"\0", 1)[0].decode("utf-8", "replace")

    def header16(self, o):
        off, count, magic = struct.unpack_from("<qiI", self.b, o)
        if magic & 0xFF != 1:
            raise MBINError(f"no list or string header at 0x{o:x} (magic 0x{magic:08x})")
        return o + off, count

    def string(self, o):
        start, length = self.header16(o)
        return self.b[start:start + length].split(b"\0", 1)[0].decode("utf-8", "replace")

    def generic(self, o):
        """A list of mixed templates: [(offset of the template, name hash)], offset None for an empty node."""
        base, count = self.header16(o)
        out = []
        for i in range(count):
            e = base + 16 * i
            off, name_hash, magic = struct.unpack_from("<qII", self.b, e)
            if magic != 0xEEEEEE01:
                raise MBINError(f"bad generic list entry at 0x{e:x}")
            out.append((e + off if off else None, name_hash))
        return out


# --- the templates -------------------------------------------------------------------------------------------------

class Template:
    """A struct: SIZE bytes, FIELDS = [(name, offset, kind, arg)]. kinds: a Reader method name; 'floats' (arg = count);
    'fixed' (arg = size); 'list' (arg = element: a Template or a (kind, size) primitive); 'strings'; 'inline'
    (arg = Template); 'generic' (arg = {name hash: Template})."""
    SIZE = 0
    FIELDS = ()

    @classmethod
    def read(cls, r, o):
        d = {}
        for name, off, kind, arg in cls.FIELDS:
            p = o + off
            if kind == "list":
                d[name] = read_list(r, p, arg)
            elif kind == "strings":
                base, count = r.header16(p)
                d[name] = [r.string(base + 16 * i) for i in range(count)]
            elif kind == "inline":
                d[name] = arg.read(r, p)
            elif kind == "generic":
                d[name] = [(arg[h].read(r, q) if q is not None and h in arg else None, h) for q, h in r.generic(p)]
            elif kind == "floats":
                d[name] = r.floats(p, arg)
            elif kind == "fixed":
                d[name] = r.fixed(p, arg)
            else:
                d[name] = getattr(r, kind)(p)
        return d


def read_list(r, o, element):
    base, count = r.header16(o)
    if isinstance(element, tuple):
        kind, size = element
        if kind == "floats4":
            return [r.floats(base + size * i, 4) for i in range(count)]
        fn = getattr(r, kind)
        return [fn(base + size * i) for i in range(count)]
    return [element.read(r, base + element.SIZE * i) for i in range(count)]


class TkTransformData(Template):
    SIZE = 0x24
    FIELDS = (("rot", 0x00, "floats", 3), ("scale", 0x0C, "floats", 3), ("trans", 0x18, "floats", 3))


class TkSceneNodeAttributeData(Template):
    SIZE = 0x20
    FIELDS = (("name", 0x00, "fixed", 0x10), ("value", 0x10, "string", None))


class TkSceneNodeData(Template):
    SIZE = 0x80
    FIELDS = (("attributes", 0x00, "list", TkSceneNodeAttributeData),
              ("children", 0x10, "list", None),   # filled below (self-reference)
              ("name", 0x30, "string", None), ("type", 0x40, "fixed", 0x10),
              ("transform", 0x50, "inline", TkTransformData), ("name_hash", 0x74, "u32", None),
              ("platform_exclusion", 0x78, "i8", None))


TkSceneNodeData.FIELDS = tuple((n, o, k, TkSceneNodeData if n == "children" else a) for n, o, k, a in TkSceneNodeData.FIELDS)


class TkResourceDescriptorData(Template):
    SIZE = 0xC8
    FIELDS = (("id", 0x00, "fixed", 0x20), ("children", 0x20, "generic", None), ("reference_paths", 0x30, "strings", None),
              ("chance", 0x40, "f32", None), ("name", 0x44, "fixed", 0x80))


class TkResourceDescriptorList(Template):
    SIZE = 0x20
    FIELDS = (("descriptors", 0x00, "list", TkResourceDescriptorData), ("type_id", 0x10, "fixed", 0x10))


class TkModelDescriptorList(Template):
    SIZE = 0x10
    FIELDS = (("list", 0x00, "list", TkResourceDescriptorList),)


TkResourceDescriptorData.FIELDS = tuple((n, o, k, {0x4026294F: TkModelDescriptorList} if n == "children" else a)
                                        for n, o, k, a in TkResourceDescriptorData.FIELDS)


class TkVertexElement(Template):
    SIZE = 0x0C
    FIELDS = (("instancing", 0x0, "u32", None), ("type", 0x4, "i32", None), ("normalise", 0x8, "u8", None),
              ("offset", 0x9, "u8", None), ("semantic", 0xA, "u8", None), ("size", 0xB, "u8", None))


class TkVertexLayout(Template):
    SIZE = 0x20
    FIELDS = (("elements", 0x00, "list", TkVertexElement), ("element_count", 0x18, "i32", None), ("stride", 0x1C, "i32", None))


class TkMeshMetaData(Template):
    SIZE = 0x38
    FIELDS = (("id", 0x00, "string", None), ("hash", 0x10, "u64", None),
              ("index_offset", 0x18, "i32", None), ("index_size", 0x1C, "i32", None),
              ("vertex_offset", 0x20, "i32", None), ("vertex_size", 0x24, "i32", None),
              ("position_offset", 0x28, "i32", None), ("position_size", 0x2C, "i32", None),
              ("double_buffer", 0x30, "u8", None))


class TkGeometryData(Template):
    SIZE = 0x160
    FIELDS = (("position_layout", 0x000, "inline", TkVertexLayout), ("vertex_layout", 0x020, "inline", TkVertexLayout),
              ("bound_hull_vert_ed", 0x040, "list", ("i32", 4)), ("bound_hull_verts", 0x050, "list", ("floats4", 16)),
              ("bound_hull_vert_st", 0x060, "list", ("i32", 4)),
              ("mesh_aabb_max", 0x0C0, "list", ("floats4", 16)), ("mesh_aabb_min", 0x0D0, "list", ("floats4", 16)),
              ("mesh_base_skin_mat", 0x0E0, "list", ("i32", 4)),
              ("mesh_vert_rend", 0x0F0, "list", ("i32", 4)), ("mesh_vert_rstart", 0x100, "list", ("i32", 4)),
              ("procgen_node_names", 0x110, "strings", None), ("procgen_parent_id", 0x120, "list", ("i32", 4)),
              ("stream_metadata", 0x140, "list", TkMeshMetaData),
              ("collision_index_count", 0x150, "i32", None), ("index_count", 0x154, "i32", None),
              ("indices_16bit", 0x158, "i32", None), ("vertex_count", 0x15C, "i32", None))


class TkMeshData(Template):
    SIZE = 0x48
    FIELDS = (("id", 0x00, "string", None), ("mesh_stream", 0x10, "header16", None),
              ("position_stream", 0x20, "header16", None), ("hash", 0x30, "u64", None),
              ("index_size", 0x38, "i32", None), ("vertex_size", 0x3C, "i32", None), ("position_size", 0x40, "i32", None))


class TkGeometryStreamData(Template):
    SIZE = 0x10
    FIELDS = (("streams", 0x00, "list", TkMeshData),)


class TkMaterialSampler(Template):
    SIZE = 0x50
    FIELDS = (("alternative_id", 0x00, "fixed", 0x20), ("map", 0x20, "string", None), ("name", 0x30, "string", None),
              ("anisotropy", 0x40, "i32", None), ("address_mode", 0x44, "u32", None), ("filter_mode", 0x48, "u32", None),
              ("is_cube", 0x4C, "u8", None), ("is_srgb", 0x4D, "u8", None), ("use_compression", 0x4E, "u8", None),
              ("use_mipmaps", 0x4F, "u8", None))


class TkMaterialUniformFloat(Template):
    SIZE = 0x30
    FIELDS = (("values", 0x00, "floats", 4), ("name", 0x20, "string", None))


class TkMaterialData(Template):
    SIZE = 0xA8
    FIELDS = (("flags", 0x00, "list", ("u32", 4)), ("fx_flags", 0x10, "list", ("u32", 4)), ("link", 0x20, "string", None),
              ("metamaterial", 0x30, "string", None), ("name", 0x40, "string", None),
              ("samplers", 0x50, "list", TkMaterialSampler), ("shader", 0x60, "string", None),
              ("uniforms", 0x70, "list", TkMaterialUniformFloat), ("transparency_layer", 0x98, "i32", None),
              ("cast_shadow", 0x9C, "u8", None), ("material_class", 0x9D, "u8", None), ("create_fur", 0x9E, "u8", None),
              ("disable_ztest", 0x9F, "u8", None), ("enable_lod_fade", 0xA0, "u8", None), ("use_shader_mill", 0xA1, "u8", None))


ROOTS = {0x3DB87E47: ("TkSceneNodeData", TkSceneNodeData), 0x4026294F: ("TkModelDescriptorList", TkModelDescriptorList),
         0x819C3220: ("TkGeometryData", TkGeometryData), 0x40025754: ("TkGeometryStreamData", TkGeometryStreamData),
         0x4737D48A: ("TkMaterialData", TkMaterialData)}

# TkMaterialData.flags values (MaterialFlagEnum, numbered from 0 in libMBIN's declaration order)
F01_DIFFUSEMAP, F03_NORMALMAP, F07_UNLIT, F16_DIFFUSE2MAP, F25_MASKS_MAP = 0, 2, 6, 15, 24
F36_DOUBLESIDED, F53_COLOURISABLE = 35, 52
MATERIAL_CLASS = {2: "Additive", 11: "Cutout", 12: "Decal", 15: "DoubleSided", 18: "Glow", 19: "GlowTranslucent",
                  45: "Opaque", 62: "Translucent", 1: "Unknown", 0: "Any"}


def header(data):
    if len(data) < HEADER:
        raise MBINError("too short for an MBIN")
    magic = struct.unpack_from("<Q", data, 0)[0]
    if magic not in (MAGIC_MBIN, MAGIC_GEOMETRY):
        raise MBINError("not an MBIN file (magic 0x%016x)" % magic)
    version, hv, name_hash = struct.unpack_from("<HHI", data, 8)
    guid = struct.unpack_from("<Q", data, 0x10)[0]
    return {"magic": magic, "version": version, "compiler_header": hv, "name_hash": name_hash, "guid": guid}


def load(data, expect=None):
    """(template name, decoded dict) of an MBIN's root; `expect` names the template it must be."""
    h = header(data)
    root = ROOTS.get(h["name_hash"])
    if root is None:
        raise MBINError("unknown root template (name hash 0x%08x)" % h["name_hash"])
    name, cls = root
    if expect and name != expect:
        raise MBINError(f"expected {expect}, found {name}")
    return name, cls.read(Reader(data), HEADER)


def attributes(node):
    """A scene node's attributes as a dict (names upper case as the game writes them)."""
    return {a["name"]: a["value"] for a in node["attributes"]}
