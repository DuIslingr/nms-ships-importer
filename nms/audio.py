"""No Man's Sky's sounds: Wwise sound banks (`AUDIO/WINDOWS/*.BNK`) with their name tables (`*.TXT`, the SoundbanksInfo
listings Wwise writes beside a bank) and the streamed sounds as `AUDIO/WINDOWS/MEDIA/<id>.WEM`.

The name table is tab-separated with one block per object kind; the `Streamed Audio` and `In Memory Audio` blocks list
every sound with its id, name, the generated `<id>.wem` (streamed sounds only) and its Wwise Object Path, the project's
folder tree (`\\Actor-Mixer Hierarchy\\Player\\Weapons\\Pl_Ship_Weapons\\Wpn_Ship_Positron_Fire\\...`), which says what a
sound is for. In-memory sounds sit in the bank itself: its `DIDX` chunk (u32 id, u32 offset, u32 size per entry)
indexes the `DATA` chunk.

The WEM files are Wwise Vorbis (fmt tag 0xFFFF): Ogg Vorbis with the headers stripped and the packets reworked, whose
codebooks are not in the file. Decoding needs an outside tool: `vgmstream-cli` (to WAV, each sound rendered once with `-i`, so a loop stays one clean pass; `ffmpeg` then makes Ogg) or
`ww2ogg` (to Ogg; `revorb` optional). None is a Python package, so the importer looks for them on the PATH.
"""
import os
import re
import shutil
import struct
import subprocess
import tempfile

PERSISTENT = "audio/windows/nms_audio_persistent"
MEDIA = "audio/windows/media/"


class Sound:
    __slots__ = ("id", "name", "file", "path", "streamed")

    def __init__(self, id, name, file, path, streamed):
        self.id, self.name, self.file, self.path, self.streamed = id, name, file, path, streamed

    def __repr__(self):
        return f"Sound({self.name}, {self.path})"


class SoundBank:
    """A bank's sounds by name and Wwise path, and their bytes (a streamed sound's .wem, an in-memory one's slice of
    the bank)."""

    def __init__(self, banks, name=PERSISTENT):
        self.banks = banks
        self.name = name
        self.sounds = []
        self.by_id = {}
        self._embedded = None
        table = name + ".txt"
        if banks.exists(table):
            self._parse(banks.read(table).decode("utf-8", "replace"))

    def _parse(self, text):
        block = None
        for line in text.splitlines():
            f = line.split("\t")
            if f[0]:
                block = f[0].strip()
                continue
            if block not in ("Streamed Audio", "In Memory Audio") or len(f) < 6 or not f[1].strip():
                continue
            sid = int(f[1]) if f[1].strip().isdigit() else f[1].strip()
            s = Sound(sid, f[2].strip(), f[4].strip().lower(), f[5].strip(), block == "Streamed Audio")
            self.sounds.append(s)
            self.by_id[sid] = s

    def find(self, pattern, name=None):
        """The sounds whose Wwise path matches `pattern` (and whose name matches `name`), in the table's order."""
        p = re.compile(pattern, re.I)
        n = re.compile(name, re.I) if name else None
        return [s for s in self.sounds if p.search(s.path) and (n is None or n.search(s.name))]

    def embedded(self):
        """{id: bytes} of the bank's in-memory sounds."""
        if self._embedded is None:
            self._embedded = {}
            bnk = self.name + ".bnk"
            if self.banks.exists(bnk):
                self._embedded = read_embedded(self.banks.read(bnk))
        return self._embedded

    def wem(self, sound):
        """The sound's WEM bytes, or None when the game lacks them."""
        if sound.streamed and sound.file:
            p = MEDIA + sound.file
            return self.banks.read(p) if self.banks.exists(p) else None
        return self.embedded().get(sound.id)


def read_embedded(data):
    """{id: bytes} from a bank's DIDX / DATA chunks."""
    pos, index, base = 0, [], None
    while pos + 8 <= len(data):
        tag = data[pos: pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = pos + 8
        if tag == b"DIDX":
            for k in range(size // 12):
                index.append(struct.unpack_from("<III", data, body + k * 12))
        elif tag == b"DATA":
            base = body
        pos = body + size
    if base is None:
        return {}
    return {sid: data[base + off: base + off + ln] for sid, off, ln in index}


class MissingDecoder(Exception):
    pass


class Decoder:
    """Turns WEM bytes into an Ogg (or WAV) file through the tools found on the PATH."""

    def __init__(self, vgmstream=None, ww2ogg=None, revorb=None, ffmpeg=None):
        # None: look on the PATH; "" (or a path): use that
        self.vgmstream = (shutil.which("vgmstream-cli") or shutil.which("vgmstream")) if vgmstream is None else vgmstream
        self.ww2ogg = shutil.which("ww2ogg") if ww2ogg is None else ww2ogg
        self.revorb = shutil.which("revorb") if revorb is None else revorb
        self.ffmpeg = shutil.which("ffmpeg") if ffmpeg is None else ffmpeg
        self.codebooks = None
        if self.ww2ogg:
            for d in (os.path.dirname(self.ww2ogg), "/usr/share/ww2ogg", "/usr/local/share/ww2ogg"):
                p = os.path.join(d, "packed_codebooks_aoTuV_603.bin")
                if os.path.exists(p):
                    self.codebooks = p
                    break

    @property
    def available(self):
        return bool(self.vgmstream or self.ww2ogg)

    def describe(self):
        if self.vgmstream:
            return "vgmstream-cli" + (" + ffmpeg (Ogg)" if self.ffmpeg else " (WAV)")
        if self.ww2ogg:
            return "ww2ogg" + (" + revorb" if self.revorb else "")
        return "none"

    def convert(self, wem, dst_base):
        """Writes `dst_base`.ogg (or .wav); returns the path written."""
        if not self.available:
            raise MissingDecoder("no WEM decoder: install vgmstream-cli (AUR: vgmstream-cli-bin) or ww2ogg and put it on the PATH")
        os.makedirs(os.path.dirname(dst_base) or ".", exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.wem")
            with open(src, "wb") as f:
                f.write(wem)
            if self.vgmstream:
                wav = os.path.join(tmp, "out.wav")
                subprocess.run([self.vgmstream, "-i", "-o", wav, src], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if self.ffmpeg:
                    dst = dst_base + ".ogg"
                    subprocess.run([self.ffmpeg, "-y", "-loglevel", "error", "-i", wav, "-c:a", "libvorbis", "-q:a", "5", dst], check=True)
                    return dst
                dst = dst_base + ".wav"
                shutil.copyfile(wav, dst)
                return dst
            dst = dst_base + ".ogg"
            cmd = [self.ww2ogg, src, "-o", dst]
            if self.codebooks:
                cmd += ["--pcb", self.codebooks]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if self.revorb:
                subprocess.run([self.revorb, dst], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return dst
