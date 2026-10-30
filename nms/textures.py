"""The game's DDS textures as PNG.

The PC game ships DXT1 (BC1), ATI1 (BC4), ATI2 (BC5) and DX10 BC7 textures, which Pillow decodes by itself. The iOS
game ships ASTC (DX10 headers, DXGI formats 134 / 142 / 150 / 162 = ASTC 4x4 / 6x6 / 8x8 / 10x10) at 256 x 256, which
Pillow doesn't: those go through the `astc_decomp_faster` (or `astc_decomp`) package when it is installed, else the
`astcenc` command when one is on the PATH (ARM's astc-encoder), else they are reported missing and the material keeps no
map. A normal map stored as ATI2 (two channels) gets its blue channel rebuilt.
"""
import io
import os
import shutil
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image

ASTC_BLOCKS = {134: (4, 4), 138: (5, 5), 142: (6, 6), 146: (8, 5), 150: (8, 8), 154: (10, 5), 158: (10, 8), 162: (10, 10),
               166: (12, 10), 170: (12, 12)}


class TextureError(Exception):
    pass


class MissingASTC(TextureError):
    pass


def dds_info(data):
    """(width, height, fourcc or 'DX10:<dxgi>', mip count) of a DDS file."""
    if data[:4] != b"DDS ":
        raise TextureError("not a DDS file")
    height, width = struct.unpack_from("<II", data, 12)
    mips = struct.unpack_from("<I", data, 28)[0]
    fourcc = data[84:88]
    kind = fourcc.decode("latin1")
    if fourcc == b"DX10":
        kind = "DX10:%d" % struct.unpack_from("<I", data, 128)[0]
    return width, height, kind, mips


_astc_module = None


def _astc():
    global _astc_module
    if _astc_module is None:
        for name in ("astc_decomp_faster", "astc_decomp"):
            try:
                _astc_module = __import__(name)
                break
            except ImportError:
                continue
        else:
            _astc_module = False
    return _astc_module


def decode_astc(data, width, height, bw, bh):
    """The top mip of an ASTC DDS as an RGBA image, through the package or the astcenc command."""
    size = ((width + bw - 1) // bw) * ((height + bh - 1) // bh) * 16
    blocks = data[148:148 + size]
    mod = _astc()
    if mod:
        if hasattr(mod, "decompress_astc"):
            px = mod.decompress_astc(blocks, width, height, bw, bh, False)
        else:
            px = mod.decompress(blocks, width, height, bw, bh)
        return Image.frombytes("RGBA", (width, height), bytes(px))
    exe = shutil.which("astcenc") or shutil.which("astcenc-avx2") or shutil.which("astcenc-sse4.1") or shutil.which("astcenc-sse2")
    if exe:
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.astc")
            dst = os.path.join(d, "out.png")
            with open(src, "wb") as f:   # the .astc container: magic, block sizes, 24-bit dims
                f.write(b"\x13\xab\xa1\x5c" + bytes([bw, bh, 1]) + width.to_bytes(3, "little") + height.to_bytes(3, "little") + (1).to_bytes(3, "little") + blocks)
            subprocess.run([exe, "-dl", src, dst], check=True, capture_output=True)
            return Image.open(dst).convert("RGBA")
    raise MissingASTC("the iOS textures are ASTC-compressed: install the astc_decomp_faster package "
                      "(python3 -m pip install astc_decomp_faster) or put ARM's astcenc on the PATH")


def decode(data):
    """A DDS file's top mip as a Pillow image (RGBA, RGB or L as Pillow gives it)."""
    width, height, kind, _ = dds_info(data)
    if kind.startswith("DX10:"):
        dxgi = int(kind[5:])
        if dxgi in ASTC_BLOCKS:
            bw, bh = ASTC_BLOCKS[dxgi]
            return decode_astc(data, width, height, bw, bh)
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


def normal_map(im):
    """A normal map as RGB with its blue channel rebuilt (BC5 keeps only red and green)."""
    arr = np.asarray(im.convert("RGB")).astype(np.float32) / 255.0
    x, y = arr[..., 0] * 2 - 1, arr[..., 1] * 2 - 1
    z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
    arr[..., 2] = (z + 1) / 2
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGB")


def masks_to_metallic_smoothness(im):
    """NMS's masks map (R ambient occlusion, G roughness, B metallic) as URP's metallic (RGB) + smoothness (A) map."""
    arr = np.asarray(im.convert("RGB"))
    out = np.zeros(arr.shape[:2] + (4,), np.uint8)
    out[..., 0] = out[..., 1] = out[..., 2] = arr[..., 2]
    out[..., 3] = 255 - arr[..., 1]
    return Image.fromarray(out, "RGBA")


def save_png(im, path, max_size=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if max_size and max(im.size) > max_size:
        s = max_size / max(im.size)
        im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    im.save(path, optimize=True)
