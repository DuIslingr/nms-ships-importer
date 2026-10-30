"""HGPAK reading on archives made here: ZSTD chunks, raw chunks, stored archives, a bank folder; no game files."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import fixtures  # noqa: E402
from fixtures import write  # noqa: E402
from nms import hgpak  # noqa: E402

try:
    from compression import zstd  # noqa: F401
    HAVE_ZSTD = True
except ImportError:
    HAVE_ZSTD = False


def files_for_test():
    big = bytes(range(256)) * 700          # 179 200 bytes: spans three 64 KiB chunks
    return {"models/common/a.scene.mbin": b"scene A", "TEXTURES/Common/b.DDS": big, "models/common/c.mbin": b"\0" * 100000}


class ArchiveTests(unittest.TestCase):
    @unittest.skipUnless(HAVE_ZSTD, "no zstd")
    def test_zstd_archive_roundtrip(self):
        files = files_for_test()
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "NMSARC.Test.pak")
            write(p, fixtures.make_hgpak(files, tail_padding=5000))
            a = hgpak.Archive(p)
            self.assertEqual(a.names, [n.lower() for n in files])
            self.assertEqual(a.chunk_size, 0x10000)
            for n, data in files.items():
                self.assertEqual(a.read(n), data, n)
            self.assertEqual(a.codec, "zstd")
            self.assertTrue("textures/common/b.dds" in a)
            self.assertFalse("missing" in a)
            with self.assertRaises(KeyError):
                a.read("missing")

    @unittest.skipUnless(HAVE_ZSTD, "no zstd")
    def test_raw_chunks_inside_a_compressed_archive(self):
        files = files_for_test()
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "NMSARC.Test.pak")
            write(p, fixtures.make_hgpak(files, raw_chunks=(0, 2)))
            a = hgpak.Archive(p)
            for n, data in files.items():
                self.assertEqual(a.read(n), data, n)

    def test_stored_archive(self):
        files = files_for_test()
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "NMSARC.Test.pak")
            write(p, fixtures.make_hgpak(files, codec=None))
            a = hgpak.Archive(p)
            self.assertFalse(a.compressed)
            self.assertIsNone(a.codec)
            for n, data in files.items():
                self.assertEqual(a.read(n), data, n)

    def test_not_an_archive(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.pak")
            write(p, b"not a pak" * 20)
            with self.assertRaises(hgpak.HGPAKError):
                hgpak.Archive(p)

    def test_sniff(self):
        self.assertEqual(hgpak.sniff_codec(b"\x28\xb5\x2f\xfd\0\0"), "zstd")
        self.assertEqual(hgpak.sniff_codec(b"\x8c\x06\0\0"), "oodle")
        self.assertEqual(hgpak.sniff_codec(b"\xf0\x11abc"), "lz4")

    def test_missing_codec_names_the_package(self):
        d = hgpak.Decompressor("oodle")
        import importlib.util
        if importlib.util.find_spec("ooz"):
            self.skipTest("pyooz is installed")
        with self.assertRaises(hgpak.MissingCodec) as cm:
            d(b"\x8c\x06\0\0\0", 100)
        self.assertIn("pyooz", str(cm.exception))


class BanksTests(unittest.TestCase):
    @unittest.skipUnless(HAVE_ZSTD, "no zstd")
    def test_folder_and_platform(self):
        with tempfile.TemporaryDirectory() as d:
            game = os.path.join(d, "No Man's Sky")
            pc = os.path.join(game, "GAMEDATA", "PCBANKS")
            os.makedirs(pc)
            write(os.path.join(pc, "NMSARC.A.pak"), fixtures.make_hgpak({"models/x.scene.mbin": b"X", "models/x.geometry.mbin.pc": b"G"}))
            write(os.path.join(pc, "NMSARC.B.pak"), fixtures.make_hgpak({"textures/y.dds": b"Y"}))
            self.assertEqual(hgpak.find_banks(game), pc)
            self.assertEqual(hgpak.find_banks(pc), pc)
            self.assertIsNone(hgpak.find_banks(d + "/nowhere"))
            b = hgpak.Banks(pc)
            self.assertEqual(b.platform, "pc")
            self.assertEqual(b.read("MODELS\\X.SCENE.MBIN"), b"X")
            self.assertEqual(b.read("textures/y.dds"), b"Y")
            self.assertTrue(b.exists("models/x.scene.mbin"))
            self.assertFalse(b.exists("models/z.scene.mbin"))
            self.assertEqual(b.glob("models/", ".mbin.pc"), ["models/x.geometry.mbin.pc"])
            self.assertEqual(b.geometry_suffix, "pc")
            ios = os.path.join(d, "app", "GAMEDATA", "IOSBANKS")
            os.makedirs(ios)
            write(os.path.join(ios, "NMSARC.A.pak"), fixtures.make_hgpak({"models/x.geometry.mbin.ios": b"G"}))
            bi = hgpak.Banks(ios)
            self.assertEqual(bi.platform, "ios")
            self.assertEqual(bi.geometry_suffix, "ios")
            self.assertEqual(hgpak.find_banks(os.path.join(d, "app")), ios)


if __name__ == "__main__":
    unittest.main()
