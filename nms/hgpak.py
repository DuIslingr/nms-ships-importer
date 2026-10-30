"""HGPAK v2 archives (No Man's Sky 5.50 and later, every platform), read with the codec their source used.

An archive (`NMSARC.*.pak`) is a header, an index of MD5-keyed entries, a chunk table and the chunks:

    0x00  "HGPAK\\0\\0\\0"
    0x08  u64 version (2)          0x10 u64 file count          0x18 u64 chunk count
    0x20  u8 compressed (+7 pad)   0x28 u64 data offset (16-aligned)
    0x30  file count x { 16-byte MD5 of the lower-cased posix path, u64 start offset (absolute), u64 decompressed size }
          chunk count x u64 stored size      (compressed archives only)
          the chunks, back to back from the data offset, each padded to 16 bytes

Entry 0 is the manifest: the names, CRLF-separated, name i belonging to entry i + 1. Decompressed, the chunks form one
stream of C bytes each (the last one shorter): a file at decompressed offset o = start - data offset spans the chunks
o // C .. ceil((o + size) / C) - 1. A chunk stored at exactly its decompressed size is raw. C and the codec come from the
platform the archive was built for, not from the header:

    PCBANKS, Windows / Linux   C = 0x10000, Zstandard (frames with the 28 B5 2F FD magic)
    PCBANKS, macOS             C = 0x20000, LZ4 block (no magic)
    IOSBANKS (and Switch)      C = 0x20000, Oodle Kraken (first byte 0x8C; Mermaid 0xCC, Leviathan 0x8A / 0xCA)

This reader finds C from the chunk count (the one of 0x10000 / 0x20000 that covers the data in that many chunks) and the
codec from the first compressed chunk, so an IOSBANKS folder copied to a PC reads as the iOS game's, a PCBANKS folder on a
Mac as the Windows game's. Zstandard needs Python 3.14's `compression.zstd` (or the `zstandard` package), LZ4 the `lz4`
package, Oodle the `pyooz` package (the open-source ooz decoder, `import ooz`); a missing one is reported by name when a
chunk needs it, not at import.
"""
import glob
import math
import os
import struct
from collections import OrderedDict

MAGIC = b"HGPAK\0\0\0"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
OODLE_FIRST_BYTES = {0x8C, 0xCC, 0x8A, 0xCA}   # Kraken, Mermaid, Leviathan block headers
CHUNK_SIZES = (0x10000, 0x20000)
CHUNK_CACHE = 96   # decompressed chunks kept per archive (small files of one folder share chunks)


class HGPAKError(Exception):
    pass


class MissingCodec(HGPAKError):
    """The chunk needs a decompressor that isn't installed; .package names the pip package."""

    def __init__(self, codec, package):
        super().__init__(f"the archive is {codec}-compressed and the {package} package is not installed "
                         f"(python3 -m pip install {package})")
        self.codec, self.package = codec, package


def _zstd():
    try:
        from compression import zstd   # Python 3.14
        return zstd.decompress
    except ImportError:
        pass
    try:
        import zstandard
        return lambda data: zstandard.ZstdDecompressor().decompress(data)
    except ImportError:
        raise MissingCodec("Zstandard", "zstandard (or Python 3.14)")


def _lz4():
    try:
        import lz4.block
    except ImportError:
        raise MissingCodec("LZ4", "lz4")
    return lambda data, size: lz4.block.decompress(data, uncompressed_size=size)


def _oodle():
    try:
        import ooz
    except ImportError:
        raise MissingCodec("Oodle", "pyooz")
    return lambda data, size: ooz.decompress(data, size)


def sniff_codec(chunk):
    """'zstd', 'oodle' or 'lz4' from a compressed chunk's first bytes (LZ4 has no magic: it is what is left)."""
    if chunk[:4] == ZSTD_MAGIC:
        return "zstd"
    if chunk and chunk[0] in OODLE_FIRST_BYTES:
        return "oodle"
    return "lz4"


class Decompressor:
    """Decompresses one archive's chunks with the codec sniffed from its first compressed chunk."""

    def __init__(self, codec=None):
        self.codec = codec
        self._fn = None

    def __call__(self, chunk, size, alternative=None):
        """`size` is the chunk's decompressed size; the last chunk of an archive may instead hold `alternative`
        (a whole chunk: the data runs past the last file's end)."""
        if len(chunk) == size or len(chunk) == alternative:
            return chunk   # stored raw
        if alternative and size < len(chunk) <= alternative and chunk[:4] != ZSTD_MAGIC:
            return chunk[:size]   # the last chunk, raw, padded past the last file
        if self.codec is None:
            self.codec = sniff_codec(chunk)
        if self._fn is None:
            if self.codec == "zstd":
                z = _zstd()
                self._fn = lambda data, n: z(data)
            elif self.codec == "oodle":
                self._fn = _oodle()
            elif self.codec == "lz4":
                self._fn = _lz4()
            else:
                raise HGPAKError(f"unknown codec {self.codec}")
        # Oodle and LZ4 need the output size. Every chunk of the iOS archives, the last one included, decompresses to
        # a whole chunk (the game pads the stream), and pyooz corrupts its heap when asked for any other amount: so a
        # whole chunk is asked for (`alternative`, the chunk size, is given for the last chunk; the others are whole).
        n = alternative or size
        try:
            return self._fn(chunk, n)
        except Exception as e:
            raise HGPAKError(f"a {self.codec} chunk failed to decompress: {e}")


class Entry:
    __slots__ = ("name", "start", "size", "index")

    def __init__(self, name, start, size, index):
        self.name, self.start, self.size, self.index = name, start, size, index

    def __repr__(self):
        return f"Entry({self.name!r}, {self.size})"


class Archive:
    """One .pak: `names` (the manifest's, lower-cased posix paths), `read(name)` -> bytes, `entries`."""

    def __init__(self, path, codec=None):
        self.path = path
        self.f = open(path, "rb")
        header = self.f.read(0x30)
        if len(header) < 0x30 or header[:8] != MAGIC:
            raise HGPAKError(f"{path} is not an HGPAK archive")
        self.version, file_count, chunk_count, compressed = struct.unpack_from("<QQQ?", header, 8)
        if self.version != 2:
            raise HGPAKError(f"{path}: HGPAK version {self.version} (only 2 is known)")
        self.data_offset = struct.unpack_from("<Q", header, 0x28)[0]
        self.compressed = compressed
        raw = self.f.read(32 * file_count)
        self._index = [struct.unpack_from("<16sQQ", raw, 32 * i) for i in range(file_count)]
        self.chunk_sizes = ()
        self.chunk_offsets = ()
        self.chunk_size = 0
        self.total = max((s + z for _, s, z in self._index), default=0) - self.data_offset
        if compressed:
            raw = self.f.read(8 * chunk_count)
            self.chunk_sizes = struct.unpack("<%dQ" % chunk_count, raw)
            offsets, o = [], self.data_offset
            for z in self.chunk_sizes:
                offsets.append(o)
                o += (z + 15) & ~15
            self.chunk_offsets = offsets
            fits = [c for c in CHUNK_SIZES if math.ceil(self.total / c) == chunk_count]
            if not fits:
                raise HGPAKError(f"{path}: {chunk_count} chunks cover {self.total} bytes with no known chunk size")
            if len(fits) > 1 and codec is None:   # a small archive: the codec tells (Zstandard archives use 0x10000)
                self.f.seek(offsets[0])
                codec = sniff_codec(self.f.read(min(16, self.chunk_sizes[0]))) if self.chunk_sizes[0] != fits[0] else None
            self.chunk_size = fits[0] if len(fits) == 1 or codec in (None, "zstd") else fits[-1]
        self.decompress = Decompressor(codec)
        self._cache = OrderedDict()
        manifest = self._read_entry(0)
        text = manifest.decode("utf-8", "replace")
        names = text.split("\r\n") if "\r\n" in text else text.split("\n")
        self.entries = [Entry(normalize(n), self._index[i + 1][1], self._index[i + 1][2], i + 1)
                        for i, n in enumerate(names) if i + 1 < len(self._index)]
        self.by_name = {e.name: e for e in self.entries}

    @property
    def names(self):
        return [e.name for e in self.entries]

    @property
    def codec(self):
        """The codec in use ('zstd', 'oodle', 'lz4'), None when the archive is stored or nothing was decompressed yet."""
        return self.decompress.codec if self.compressed else None

    def __contains__(self, name):
        return name.lower() in self.by_name

    def __len__(self):
        return len(self.entries)

    def _chunk(self, i):
        c = self._cache.get(i)
        if c is not None:
            self._cache.move_to_end(i)
            return c
        self.f.seek(self.chunk_offsets[i])
        stored = self.f.read(self.chunk_sizes[i])
        expected = min(self.chunk_size, self.total - i * self.chunk_size)
        c = self.decompress(stored, expected, self.chunk_size if expected < self.chunk_size else None)
        self._cache[i] = c
        if len(self._cache) > CHUNK_CACHE:
            self._cache.popitem(last=False)
        return c

    def _read_entry(self, i):
        _, start, size = self._index[i]
        if not self.compressed:
            self.f.seek(start)
            return self.f.read(size)
        o = start - self.data_offset
        c = self.chunk_size
        first, last = o // c, math.ceil((o + size) / c)
        parts = [self._chunk(k) for k in range(first, last)]
        data = parts[0] if len(parts) == 1 else b"".join(parts)
        skip = o - first * c
        return data[skip:skip + size]

    def read(self, name):
        e = self.by_name.get(name.lower())
        if e is None:
            raise KeyError(name)
        return self._read_entry(e.index)

    def close(self):
        self.f.close()


def normalize(name):
    """A game path as the manifests spell it: lower case, forward slashes, no leading slash."""
    return name.replace("\\", "/").lstrip("/").lower()


class Banks:
    """A PCBANKS or IOSBANKS folder: every archive in it, found by name across them (`read`, `exists`, `find`).

    `platform` is 'ios' when the folder is named IOSBANKS or holds '.mbin.ios' geometry, 'pc' otherwise (the Windows,
    Linux and macOS games all keep the PC file names); `geometry_suffix` is the suffix of the geometry files there.
    Archives open lazily: their manifests are read the first time a name is looked up.
    """

    def __init__(self, folder, codec=None):
        self.folder = folder
        self.paths = sorted(glob.glob(os.path.join(folder, "*.pak")))
        if not self.paths:
            raise HGPAKError(f"no .pak archives in {folder}")
        self.codec = codec
        self._archives = {}
        self._where = None
        self.platform = "ios" if os.path.basename(os.path.normpath(folder)).lower() == "iosbanks" else "pc"

    def archive(self, path):
        a = self._archives.get(path)
        if a is None:
            a = self._archives[path] = Archive(path, self.codec)
        return a

    def _map(self):
        if self._where is None:
            where = {}
            for p in self.paths:
                for n in self.archive(p).names:
                    where.setdefault(n, p)
            self._where = where
            if any(n.endswith(".geometry.mbin.ios") for n in where):
                self.platform = "ios"
        return self._where

    @property
    def geometry_suffix(self):
        return "ios" if self.platform == "ios" else "pc"

    @property
    def names(self):
        return sorted(self._map())

    def find(self, name):
        p = self._map().get(normalize(name))
        return self.archive(p) if p else None

    def exists(self, name):
        return normalize(name) in self._map()

    def read(self, name):
        a = self.find(name)
        if a is None:
            raise KeyError(name)
        return a.read(normalize(name))

    def glob(self, prefix="", suffix=""):
        prefix, suffix = normalize(prefix), suffix.lower()
        return [n for n in self.names if n.startswith(prefix) and n.endswith(suffix)]

    def close(self):
        for a in self._archives.values():
            a.close()


def find_banks(path):
    """The banks folder of a game install or a banks folder itself: <game>/GAMEDATA/PCBANKS or IOSBANKS, the .app's
    GAMEDATA on iOS, or the folder given when it holds .pak files."""
    path = os.path.abspath(os.path.expanduser(path))
    candidates = [path,
                  os.path.join(path, "GAMEDATA", "PCBANKS"), os.path.join(path, "GAMEDATA", "IOSBANKS"),
                  os.path.join(path, "PCBANKS"), os.path.join(path, "IOSBANKS")]
    for c in candidates:
        if os.path.isdir(c) and glob.glob(os.path.join(c, "*.pak")):
            return c
    for root, dirs, files in os.walk(path):
        if root.count(os.sep) - path.count(os.sep) > 6:
            dirs[:] = []
            continue
        if os.path.basename(root).upper() in ("PCBANKS", "IOSBANKS") and any(f.endswith(".pak") for f in files):
            return root
    return None
