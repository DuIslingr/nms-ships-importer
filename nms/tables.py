"""The reality tables the mod reads besides the models: the technology table (the ship weapons' numbers) and the
English texts. Both are 7.x MBINs read by their fixed layouts (see research/formats.md, "Tables"):

- `metadata/reality/tables/nms_reality_gctechnologytable.mbin`: an array of GcTechnology entries of 736 bytes
  whose ID string sits 264 bytes into the entry (the icon path's and the description text id's headers lie before
  it, the name and subtitle, the requirements and the stat bonuses after it, the variable-size ones as 16-byte
  list headers: i64 offset from the header, i32 count, u32 magic). A stat bonus is (f32 value, i32 level,
  u32 stat type); the stat types are the game's GcStatsTypes enum, whose ship-weapon part is numbered here from
  the Photon Cannon's own entry (damage 320, rate 7.5, range 1500 ... in the order of the enum's names in the binary).
- `language/*_english.mbin`: arrays of 304-byte entries, a 0x20 id then one 16-byte string header per language;
  the first non-empty one is the text.
"""
import re
import struct

TECH_TABLE = "metadata/reality/tables/nms_reality_gctechnologytable.mbin"
TECH_STRIDE = 736
LANG_STRIDE = 304
STAT_NAMES = {120: "Guns_Damage", 121: "Guns_Rate", 122: "Guns_HeatTime", 123: "Guns_CoolTime", 124: "Guns_Scale",
              125: "Guns_BulletsPerShot", 126: "Guns_Dispersion", 127: "Guns_Range", 128: "Guns_Damage_Radius",
              129: "Lasers", 130: "Lasers_Damage", 131: "Lasers_HeatTime", 141: "ShieldLeech"}

_TECH_ID = re.compile(rb"^[A-Z][A-Z0-9_]{1,15}(\0|\Z)")
_TEXT_ID = re.compile(rb"^[A-Za-z0-9_][!-~]{0,31}(\0|\Z)")


def _cstr(b):
    return b.split(b"\0", 1)[0].decode("latin1")


def _header(data, at):
    rel, n, magic = struct.unpack_from("<qIi", data, at)
    return at + rel, n, magic


def _vstr(data, at):
    """A VariableSizeString field: its 16-byte header at `at`."""
    start, n, _ = _header(data, at)
    return _cstr(data[start: start + n]) if 0 < n < 4096 and 0 <= start < len(data) else ""


def _is_id(data, at, width, pattern):
    return bool(pattern.match(data[at: at + width]))


def _entries_start(data, stride, width, pattern):
    """(offset of the first entry's id, entry count) of the table's array (the list header at 0x20: its entries are
    `stride` bytes, the id field found where an id-like string sits in the first three entries alike)."""
    start, count, _ = _header(data, 0x20)
    if count <= 0 or start < 0x20 or start + stride > len(data):
        return None, 0
    for o in range(0, stride, 8):
        if all(_is_id(data, start + k * stride + o, width, pattern) for k in range(min(3, count)) if start + k * stride + o + width <= len(data)):
            return start + o, count
    return None, 0


def _sane(data, start, n, size):
    return 0 <= start and start + n * size <= len(data)


def technologies(data):
    """{id: {"name": text id, "subtitle": text id, "description": text id, "icon": texture path,
    "stats": {stat name or number: value}, "requirements": [(item id, amount)]}} of a technology table."""
    start, count = _entries_start(data, TECH_STRIDE, 16, _TECH_ID)
    if start is None:
        return {}
    out = {}
    for k in range(count):
        e = start + k * TECH_STRIDE
        if e + TECH_STRIDE > len(data) + 264:
            break
        tid = _cstr(data[e: e + 16])
        if not tid:
            continue
        stats = {}
        st, n, _ = _header(data, e + 0x50)
        if not _sane(data, st, min(n, 64), 12):
            n = 0
        for k in range(min(n, 64)):
            v, level, kind = struct.unpack_from("<fii", data, st + k * 12)
            stats[STAT_NAMES.get(kind, kind)] = v
        reqs = []
        rs, rn, _ = _header(data, e + 0x30)
        if not _sane(data, rs, min(rn, 16), 0x18):
            rn = 0
        for k in range(min(rn, 16)):
            reqs.append((_cstr(data[rs + k * 0x18: rs + k * 0x18 + 16]), struct.unpack_from("<i", data, rs + k * 0x18 + 16)[0]))
        # the entry begins 264 bytes before its ID: the icon's and the description's headers lie there
        out[tid] = {"name": _cstr(data[e + 0xbc: e + 0xfc]), "subtitle": _vstr(data, e + 0x60), "description": _vstr(data, e - 0x10),
                    "icon": _vstr(data, e - 0x58).replace("\\", "/").lower(), "stats": stats, "requirements": reqs}
    return out


def english(datas):
    """{text id: English text} over the language files' contents (the `*_english.mbin` files)."""
    texts = {}
    for data in datas:
        start, count = _entries_start(data, LANG_STRIDE, 0x20, _TEXT_ID)
        if start is None:
            continue
        for k in range(count):
            e = start + k * LANG_STRIDE
            if e + LANG_STRIDE > len(data):
                break
            tid = _cstr(data[e: e + 0x20])
            if not tid:
                continue
            for o in range(0x20, LANG_STRIDE, 16):
                st, n, _ = _header(data, e + o)
                if 0 < n < 8192 and _sane(data, st, n, 1):
                    texts[tid] = data[st: st + n].split(b"\0", 1)[0].decode("utf-8", "replace")
                    break
    return texts


def english_files(banks):
    return [n for n in banks.names if n.lower().startswith("language/") and n.lower().endswith("_english.mbin")]


_TAGS = re.compile(r"<[A-Z]*>|<>")


def plain(text):
    """A game text without its markup tags (<TECHNOLOGY>...<>) and without the sentences that name a control
    (<IMG>SHIPFIRE<>: "Press ... to fire")."""
    text = _TAGS.sub("", re.sub(r"<IMG>[A-Z_]*<>", "\x01", text))
    text = re.sub(r"\s*\n\s*", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(x for x in sentences if "\x01" not in x).strip()
