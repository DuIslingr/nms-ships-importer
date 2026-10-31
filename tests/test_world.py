"""The stations, the hostile drones and the weapons on a synthetic game: a station scene with an exterior subtree and
an interior, a descriptor choosing its shape, a docking tunnel on its left; a drone scene from the robots folder; a
technology table and an English language file in the game's own layouts. No game files."""
import json
import math
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import fixtures  # noqa: E402
import build  # noqa: E402
import glb  # noqa: E402
import weapons  # noqa: E402
import world  # noqa: E402
from nms import hgpak, tables  # noqa: E402

try:
    from compression import zstd  # noqa: F401
    HAVE_ZSTD = True
except ImportError:
    HAVE_ZSTD = False

MAT = "MODELS\\SPACE\\TEST\\PRIMARY.MATERIAL.MBIN"


def box(cx, cy, cz, s=0.5):
    pos = np.array([[cx + sx * s, cy + sy * s, cz + sz * s] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], np.float32)
    uv = np.zeros((8, 2), np.float32)
    n = np.array([[0, 0, 1]] * 8, np.float32)
    idx = np.array([[0, 1, 2], [1, 3, 2], [4, 6, 5], [5, 6, 7], [0, 4, 1], [1, 4, 5], [2, 3, 6], [3, 7, 6], [0, 2, 4], [2, 6, 4], [1, 5, 3], [3, 7, 5]], np.uint32)
    return pos, uv, n, idx


def mesh(name, lod=0):
    return {"name": name, "type": "MESH", "attrs": {"LODLEVEL": str(lod), "MATERIAL": MAT}}


def station_game(folder):
    """A station: _STATION_ picks Cub or Oct; the Cub's node holds Station_Cub (the interior, a big box with no LODs)
    and Outside_Cub (the hull: a 100 m box with LOD0 and LOD1, a dome 60 m to its +X side) and a TunnelOpening
    locator at its -X face; the Oct's node has a hull of its own. A drone in the robots folder faces -Z."""
    files = {}
    tex = fixtures.make_dds_dxt1()
    files["textures/space/test/primary.dds"] = tex
    files["models/space/test/primary.material.mbin"] = fixtures.make_material("Station_Mat", 45, "TEXTURES/SPACE/TEST/PRIMARY.DDS")
    base = "models/space/test/station"
    g, d = fixtures.make_geometry({"HULLLOD0": box(0, 0, 0, 50.0), "HULLLOD1": box(0, 0, 0, 49.0), "DOMELOD0": box(80, 0, 0, 10.0), "DOMELOD1": box(80, 0, 0, 9.0),
                                   "INTERIORLOD0": box(0, 0, 0, 40.0), "OCTLOD0": box(0, 0, 0, 30.0), "OCTLOD1": box(0, 0, 0, 29.0)})
    files[base + ".geometry.mbin.pc"] = g
    files[base + ".geometry.data.mbin.pc"] = d
    files[base + ".scene.mbin"] = fixtures.make_scene({
        "name": base.upper().replace("/", "\\"), "type": "MODEL", "attrs": {"GEOMETRY": base.upper().replace("/", "\\") + ".GEOMETRY.MBIN"},
        "children": [
            {"name": "_Station_Cub", "type": "LOCATOR", "children": [
                {"name": "Station_Cub", "type": "LOCATOR", "children": [mesh("InteriorLOD0")]},
                {"name": "Outside_Cub", "type": "LOCATOR", "children": [mesh("HullLOD0"), mesh("HullLOD1", 1), mesh("DomeLOD0"), mesh("DomeLOD1", 1),
                                                                           {"name": "TunnelOpening", "type": "LOCATOR", "transform": ((0, 0, 0), (1, 1, 1), (-50, 0, 0))}]}]},
            {"name": "_Station_Oct", "type": "LOCATOR", "children": [
                {"name": "Outside_Oct", "type": "LOCATOR", "children": [mesh("OctLOD0"), mesh("OctLOD1", 1)]}]}]})
    files[base + ".descriptor.mbin"] = fixtures.make_descriptor([{"type": "_STATION_", "options": [
        {"id": "_STATION_CUB", "name": "_Station_Cub", "chance": 1.0}, {"id": "_STATION_OCT", "name": "_Station_Oct", "chance": 1.0}]}])
    # the drone: a body behind (+Z) and an eye in front (-Z)
    drone = "models/common/robots/testdrone"
    g, d = fixtures.make_geometry({"BODYLOD0": box(0, 0, 0.5, 0.5), "EYELOD0": box(0, 0, -0.8, 0.2)})
    files[drone + ".geometry.mbin.pc"] = g
    files[drone + ".geometry.data.mbin.pc"] = d
    files[drone + ".scene.mbin"] = fixtures.make_scene({
        "name": drone.upper().replace("/", "\\"), "type": "MODEL", "attrs": {"GEOMETRY": drone.upper().replace("/", "\\") + ".GEOMETRY.MBIN"},
        "children": [mesh("BodyLOD0"), mesh("EyeLOD0"), mesh("CritMesh"), mesh("PatrolEye"), {"name": "J_Eye", "type": "JOINT", "transform": ((0, 0, 0), (1, 1, 1), (0, 0, -0.7))}]})
    # the technology table and the texts
    files[tables.TECH_TABLE] = make_tech_table([
        dict(id="SHIPGUN1", name="SHIPGUN1_NAME", subtitle="SHIPGUN1_SUBTITLE", description="SHIPGUN1_DESCRIPTION", icon="TEXTURES/UI/TEST/GUN.DDS",
             stats=[(121, 7.5), (126, 0.0), (125, 1.0), (122, 7.5), (120, 320.0), (127, 1500.0), (124, 6.0), (123, 1.0), (128, 2.0)], reqs=[("LAND2", 100)]),
        dict(id="SHIPLAS1", name="SHIPLAS1_NAME", subtitle="SHIPLAS1_SUBTITLE", description="SHIPLAS1_DESCRIPTION", icon="TEXTURES/UI/TEST/BEAM.DDS",
             stats=[(129, 1.0), (131, 2.5), (130, 250.0), (141, 0.2)], reqs=[]),
        dict(id="SHIPROCKETS", name="SHIP_ROCKETS_NAME", subtitle="SHIP_ROCKETS_SUB", description="SHIP_ROCKETS_DESC", icon="TEXTURES/UI/TEST/ROCKET.DDS",
             stats=[(121, 1.0), (120, 6500.0), (127, 5000.0), (123, 10.0), (128, 15.0)], reqs=[])])
    files["language/nms_loc1_english.mbin"] = make_language({
        "SHIPGUN1_NAME": "PHOTON CANNON", "SHIPGUN1_SUBTITLE": "Starship Projectile Weapon",
        "SHIPGUN1_DESCRIPTION": "A destructive <TECHNOLOGY>starship projectile launcher<>.\n\nUse <IMG>CYCLEWEAPON<> to change weapon mode. Press <IMG>SHIPFIRE<> to fire.",
        "SHIPLAS1_NAME": "PHASE BEAM", "SHIPLAS1_SUBTITLE": "Starship Energy Weapon", "SHIPLAS1_DESCRIPTION": "A beam.",
        "SHIP_ROCKETS_NAME": "ROCKET LAUNCHER", "SHIP_ROCKETS_SUB": "Long Range Starship Weapon", "SHIP_ROCKETS_DESC": "A rocket."})
    files["textures/ui/test/gun.dds"] = tex
    files["textures/ui/test/beam.dds"] = tex
    files["textures/ui/test/rocket.dds"] = tex
    files[weapons.IMPACT] = tex
    files[weapons.MUZZLE] = tex
    files["textures/effects/lines/shipgun.dds"] = tex
    files["textures/effects/weapons/grenadeplasma.dds"] = tex
    pc = os.path.join(folder, "GAMEDATA", "PCBANKS")
    os.makedirs(pc)
    fixtures.write(os.path.join(pc, "NMSARC.World.pak"), fixtures.make_hgpak(files))
    return pc


def make_tech_table(entries):
    """A technology table in the game's layout: the list header at 0x20, entries of 736 bytes with the ID 264 bytes in,
    the icon's and the description's string headers before it, the name and subtitle, the requirements and the stat
    bonuses after it."""
    w = fixtures.MbinWriter(0x14FDBFDE)
    hdr = w.alloc(16)
    base = w.alloc(tables.TECH_STRIDE * len(entries))
    w.header(hdr, base, len(entries))
    for i, e in enumerate(entries):
        at = base + i * tables.TECH_STRIDE + 264
        w.string(at - 0x58, e["icon"])
        w.string(at - 0x10, e["description"])
        w.fixed(at, e["id"], 0x10)
        w.fixed(at + 0xbc, e["name"], 0x40)
        w.string(at + 0x60, e["subtitle"])
        reqs = w.alloc(0x18 * len(e["reqs"]))
        w.header(at + 0x30, reqs, len(e["reqs"]))
        for k, (rid, amount) in enumerate(e["reqs"]):
            w.fixed(reqs + 0x18 * k, rid, 0x10)
            w.put(reqs + 0x18 * k + 0x10, "<i", amount)
        stats = w.alloc(12 * len(e["stats"]))
        w.header(at + 0x50, stats, len(e["stats"]))
        for k, (kind, value) in enumerate(e["stats"]):
            w.put(stats + 12 * k, "<fii", value, 1, kind)
    return w.done()


def make_language(texts):
    """A language file: entries of 304 bytes, a 0x20 id then the languages' string headers (the English one third)."""
    w = fixtures.MbinWriter(0x6C8AA4C7)
    hdr = w.alloc(16)
    base = w.alloc(tables.LANG_STRIDE * len(texts))
    w.header(hdr, base, len(texts))
    for i, (tid, text) in enumerate(texts.items()):
        at = base + i * tables.LANG_STRIDE
        w.fixed(at, tid, 0x20)
        w.string(at + 0x40, text)
    return w.done()


@unittest.skipUnless(HAVE_ZSTD, "no zstd")
class WorldTests(unittest.TestCase):
    def test_station_models_systems_and_stations(self):
        """A station model per shape, the exterior only, turned so its tunnel faces +Z, in the systems' entries;
        a structure that can't be docked at, the Anomaly roaming."""
        with tempfile.TemporaryDirectory() as d:
            pc = station_game(d)
            out = os.path.join(d, "nms_ships")
            saved = (dict(world.STATIONS), list(world.SYSTEMS), dict(world.ANOMALY))
            world.STATIONS.clear()
            world.STATIONS.update({
                "cube": dict(scene="models/space/test/station", name="Cube", picks=["_Station_Cub"], keep=r"/_?Outside_", lod_budget=100000),
                "oct": dict(scene="models/space/test/station", name="Oct", picks=["_Station_Oct"], keep=r"/_?Outside_", lod_budget=100000, scale=2.0),
                "anomaly": dict(scene="models/space/test/station", name="Anomaly", picks=["_Station_Oct"], keep=r"/_?Outside_", lod_budget=100000)})
            world.SYSTEMS[:] = [dict(id="alpha", name="Alpha", race=0, security=2, position=[90, 90, 90], sky=1, gates=[30, "beta"],
                                     stations=[dict(id="alpha_wreck", model="oct", name="Wreck", planet=3, dock=False, subtitle="Wreck", description="A wreck."),
                                               dict(id="alpha_station", model="cube", name="Alpha Station", techLevel=6, planet=2, subtitle="Station", description="A station.")]),
                                dict(id="beta", name="Beta", race=1, security=1, position=[95, 90, 90], sky=2, gates=[],
                                     stations=[dict(id="beta_station", model="missing", name="Nowhere", techLevel=1, planet=1)])]
            world.ANOMALY.update(system="alpha")
            try:
                kits, ships, report = build.build(hgpak.Banks(pc), out, ["cube", "oct", "anomaly"])
            finally:
                world.STATIONS.clear()
                world.STATIONS.update(saved[0])
                world.SYSTEMS[:] = saved[1]
                world.ANOMALY.update(saved[2])
            self.assertEqual(report.warnings, [])
            self.assertEqual((kits, ships), ([], []))
            systems = json.load(open(os.path.join(out, "systems.json")))
            stations = json.load(open(os.path.join(out, "stations.json")))
            self.assertEqual([s["id"] for s in systems], ["alpha"])   # beta's only station has no model: no system
            self.assertEqual(systems[0]["gates"], [30, "nms_ships:beta"])
            self.assertEqual(systems[0]["gateStation"], "nms_ships:alpha_station")   # the dockable one leads, as the gate orbit
            self.assertEqual(systems[0]["traffic"], "mod")
            self.assertEqual([s["id"] for s in stations], ["alpha_station", "alpha_wreck", "space_anomaly"])
            station = stations[0]
            self.assertEqual(station["system"], "nms_ships:alpha")
            self.assertEqual(station["model"], "models/cube.glb")
            self.assertAlmostEqual(station["modelSize"], 140 * 20, places=3)   # the hull (-50..50) and the dome (70..90): 140 m, in game units
            self.assertEqual(station["collision"], "box")
            self.assertNotIn("orbit", station)
            self.assertEqual(stations[1]["orbit"], {"station": "nodock"})
            self.assertAlmostEqual(stations[1]["modelSize"], 60 * 2 * 20, places=3)   # scaled x2
            self.assertEqual(stations[2]["mobile"]["route"], "any")
            self.assertTrue(all("mesh" in m and m["mesh"].startswith("__mat_") for m in station["materials"]))
            doc, binary = glb.read(os.path.join(out, "models/cube.glb"))
            names = [n["name"] for n in doc["nodes"]]
            self.assertTrue(any("HullLOD0" in n for n in names))
            self.assertTrue(any("DomeLOD0" in n for n in names))
            self.assertFalse(any("Interior" in n for n in names))   # the interior subtree is left out
            self.assertFalse(any("Oct" in n for n in names))         # the other shape too
            # turned: the tunnel was at -X, so the dome (at +X) now lies at -Z
            acc = doc["accessors"]
            dome = next(n for n in doc["nodes"] if "DomeLOD0" in n["name"])
            prim = doc["meshes"][dome["mesh"]]["primitives"][0]
            a = acc[prim["attributes"]["POSITION"]]
            self.assertLess(a["max"][2], -60)
            self.assertLess(abs(a["max"][0]), 15)

    def test_hostile_drone_from_the_robots_folder(self):
        """A traffic-only craft from a scene outside the spacecraft folder, turned round when it looks along -Z, its
        critical-hit mesh and patrol eye left out."""
        with tempfile.TemporaryDirectory() as d:
            pc = station_game(d)
            out = os.path.join(d, "nms_ships")
            build.CLASSES["test_drone"] = dict(backward=True, scene="models/common/robots/testdrone", name="Test Drone", scale=6.0, armor=120, cargo=5, handling=190,
                                               price=0, race=9, equipment=4, traffic_only=True, hostile=True, description="A drone.")
            try:
                kits, ships, report = build.build(hgpak.Banks(pc), out, ["test_drone"])
            finally:
                del build.CLASSES["test_drone"]
            self.assertEqual(report.warnings, [])
            self.assertEqual(kits[0]["yaw"], 180)
            self.assertEqual(ships[0]["traffic"], {"weight": 1, "races": [9]})
            self.assertNotIn("dealer", ships[0])
            doc, _ = glb.read(os.path.join(out, kits[0]["parts"][0]["model"]))
            names = [n["name"] for n in doc["nodes"] if "mesh" in n]
            self.assertEqual(len(names), 2)
            self.assertFalse(any("CritMesh" in n or "PatrolEye" in n for n in names))

    def test_weapons_from_the_technology_table(self):
        """The weapons' items: the table's numbers scaled to the remake's, the texts' names, the icons and bolts as PNGs."""
        with tempfile.TemporaryDirectory() as d:
            pc = station_game(d)
            out = os.path.join(d, "nms_ships")
            kits, ships, report = build.build(hgpak.Banks(pc), out, ["photon_cannon", "phase_beam", "rocket_launcher", "cyclotron_ballista"])
            self.assertEqual([w for w in report.warnings if "SHIPPLASMA" not in w], [])   # the cyclotron is not in this table
            items = json.load(open(os.path.join(out, "items.json")))
            self.assertEqual([i["id"] for i in items], ["photon_cannon", "phase_beam", "rocket_launcher"])
            gun = items[0]
            self.assertEqual(gun["base"], 12)
            self.assertEqual(gun["name"], {"en": "Photon Cannon"})
            self.assertEqual(gun["description"], "Starship Projectile Weapon. A destructive starship projectile launcher.")
            self.assertEqual(gun["stats"], {"damage": 2, "reloadMs": 133, "speed": 14, "lifetimeMs": 2142})   # 320 / 150; 1000 / 7.5; 1500 m at 14 units/ms
            self.assertEqual(gun["fx"]["projectile"]["sprite"], "fx/photon_cannon_bolt.png")
            self.assertTrue(os.path.exists(os.path.join(out, "fx/photon_cannon_bolt.png")))
            self.assertEqual(gun["icon"], "fx/icons/photon_cannon.png")
            from PIL import Image
            self.assertEqual(Image.open(os.path.join(out, gun["icon"])).size, (180, 88))
            beam = items[1]
            self.assertEqual(beam["stats"], {"damage": 8, "reloadMs": 1200, "lifetimeMs": 2400, "shieldDamage": 200})
            self.assertNotIn("impact", beam["fx"])
            rocket = items[2]
            self.assertEqual(rocket["stats"], {"damage": 43, "reloadMs": 10000, "blastRadius": 300, "speed": 16, "lifetimeMs": 6250})
            self.assertNotIn("muzzle", rocket["fx"])
            mod = json.load(open(os.path.join(out, "mod.json")))
            self.assertIn("Photon Cannon", mod["description"])


class TablesTests(unittest.TestCase):
    def test_plain_text(self):
        self.assertEqual(tables.plain("A <TECHNOLOGY>beam<> weapon.\n\nPress <IMG>SHIPFIRE<> to fire. Done."), "A beam weapon. Done.")


if __name__ == "__main__":
    unittest.main()


def make_bank_table(rows):
    """A Wwise SoundbanksInfo listing: (name, streamed file or None, path) rows, in-memory ones in their own block."""
    out = ["Event\tID\tName\t\t\tWwise Object Path\tNotes", "\t1\tPlay_Thing\t\t\t\\Events\\Play_Thing\t", ""]
    out.append("Streamed Audio\tID\tName\tAudio source file\tGenerated audio file\tWwise Object Path\tNotes")
    for i, (name, file, path) in enumerate(rows):
        if file:
            out.append(f"\t{1000 + i}\t{name}\tU:\\src\\{name}.wav\t{file}\t{path}\t")
    out.append("")
    out.append("In Memory Audio\tID\tName\tAudio source file\tGenerated audio file\tWwise Object Path\tNotes")
    for i, (name, file, path) in enumerate(rows):
        if not file:
            out.append(f"\t{1000 + i}\t{name}\tU:\\src\\{name}.wav\t\t{path}\t")
    return "\n".join(out).encode()


def make_bnk(embedded):
    """A bank with a DIDX / DATA pair holding {id: bytes}."""
    import struct
    data = b"".join(embedded.values())
    didx, off = b"", 0
    for sid, blob in embedded.items():
        didx += struct.pack("<III", sid, off, len(blob))
        off += len(blob)
    return b"BKHD" + struct.pack("<I", 8) + b"\0" * 8 + b"DIDX" + struct.pack("<I", len(didx)) + didx + b"DATA" + struct.pack("<I", len(data)) + data


class FakeDecoder:
    available = True

    def convert(self, wem, base):
        with open(base + ".ogg", "wb") as f:
            f.write(b"OggS" + wem)
        return base + ".ogg"


class SoundTests(unittest.TestCase):
    def bank(self, d):
        from nms import audio
        rows = [("Pl_Ship_Fighter_Space_Speed2_Rr", "1000.wem", "\\Actor-Mixer Hierarchy\\Player\\Ship\\Pl_Ship\\Pl_Ship_Engines\\Pl_Ship_Engines_Fighter\\Pl_Ship_Space\\Pl_Ship_Fighter_Space_Speed2_Rr"),
                ("Pl_ShiP_Boost_Start_01", "1001.wem", "\\Actor-Mixer Hierarchy\\Player\\Ship\\Pl_Ship\\Pl_Ship_Boost\\Ship_Boost_Start_Type\\Pl_Ship_Boost_Start\\Pl_ShiP_Boost_Start_01"),
                ("Pl_ShiP_Boost_Start_02", None, "\\Actor-Mixer Hierarchy\\Player\\Ship\\Pl_Ship\\Pl_Ship_Boost\\Ship_Boost_Start_Type\\Pl_Ship_Boost_Start\\Pl_ShiP_Boost_Start_02"),
                ("Pl_Ship_Laser01_01", "1003.wem", "\\Actor-Mixer Hierarchy\\Player\\Weapons\\Pl_Ship_Weapons\\Wpn_Pl_Ship_Gun\\Wpn_Ship_Laser_Class_01_Layer_01\\Pl_Ship_Laser01_01"),
                ("Pl_Ship_Laser01_01", "1003.wem", "\\Actor-Mixer Hierarchy\\Player\\Weapons\\Pl_Ship_Weapons\\Wpn_Pl_Ship_Gun\\Wpn_Ship_Laser_Class_01_Layer_01\\Pl_Ship_Laser01_01"),
                ("Drone_Engine_Rear_01", "1005.wem", "\\Actor-Mixer Hierarchy\\NPCs\\NPC_Ships\\NPC_Ship_Engines\\NPC_Ship_Engine_Drone\\Drone_Engine_Rear_01")]
        files = {audio.PERSISTENT + ".txt": make_bank_table(rows), audio.PERSISTENT + ".bnk": make_bnk({1002: b"RIFF-mem"}),
                 audio.MEDIA + "1000.wem": b"RIFF-eng", audio.MEDIA + "1001.wem": b"RIFF-bs1", audio.MEDIA + "1003.wem": b"RIFF-gun", audio.MEDIA + "1005.wem": b"RIFF-drn"}
        pc = os.path.join(d, "GAMEDATA", "PCBANKS")
        os.makedirs(pc)
        fixtures.write(os.path.join(pc, "NMSARC.Audio.pak"), fixtures.make_hgpak(files))
        return hgpak.Banks(pc)

    @unittest.skipUnless(HAVE_ZSTD, "no zstd")
    def test_bank_and_sounds_on_ships_and_weapons(self):
        """The bank's table and its embedded sounds are read; a fighter gets its engine loop and both boost starts (one
        streamed, one in the bank), a drone its own loop, a capital ship none here; the photon cannon its shot (the
        duplicate row once); the files land in audio/."""
        import sounds
        from nms import audio
        with tempfile.TemporaryDirectory() as d:
            banks = self.bank(d)
            bank = audio.SoundBank(banks)
            self.assertEqual(len(bank.sounds), 6)
            self.assertEqual(bank.wem(bank.find(r"Boost_Start", r"_02$")[0]), b"RIFF-mem")
            out = os.path.join(d, "mod")
            os.makedirs(out)
            ships = [{"id": "fighter", "kit": "fighter"}, {"id": "sentinel_drone", "kit": "sentinel_drone"}, {"id": "freighter"}]
            items = [{"id": "photon_cannon", "fx": {}}, {"id": "phase_beam"}]
            report = build.Report()
            n = sounds.apply(banks, out, report, ships, items, decoder=FakeDecoder(), bank=bank)
            self.assertEqual(report.warnings, [])
            self.assertEqual(n, 5)   # the engine, two boost starts, the shot, the drone loop
            self.assertEqual(ships[0]["sounds"]["engine"]["file"], "audio/Pl_Ship_Fighter_Space_Speed2_Rr.ogg")
            self.assertEqual(ships[0]["sounds"]["boostStart"]["files"], ["audio/Pl_ShiP_Boost_Start_01.ogg", "audio/Pl_ShiP_Boost_Start_02.ogg"])
            self.assertNotIn("boostLoop", ships[0]["sounds"])
            self.assertEqual(ships[1]["sounds"], {"engine": {"file": "audio/Drone_Engine_Rear_01.ogg", "volume": [0.15, 0.27], "pitch": [0.9, 1.1]}})
            self.assertNotIn("sounds", ships[2])
            self.assertEqual(items[0]["fx"], {"shot": "audio/Pl_Ship_Laser01_01.ogg", "shotLoops": False})
            self.assertNotIn("fx", items[1])
            with open(os.path.join(out, "audio/Pl_ShiP_Boost_Start_02.ogg"), "rb") as f:
                self.assertEqual(f.read(), b"OggSRIFF-mem")

    @unittest.skipUnless(HAVE_ZSTD, "no zstd")
    def test_no_decoder_leaves_the_mod_without_sounds(self):
        import sounds
        from nms import audio
        with tempfile.TemporaryDirectory() as d:
            banks = self.bank(d)
            ships = [{"id": "fighter", "kit": "fighter"}]
            report = build.Report()
            n = sounds.apply(banks, d, report, ships, [], decoder=audio.Decoder(vgmstream="", ww2ogg="", revorb="", ffmpeg=""), bank=audio.SoundBank(banks))
            self.assertEqual(n, -1)
            self.assertNotIn("sounds", ships[0])
            self.assertEqual(len(report.warnings), 1)
