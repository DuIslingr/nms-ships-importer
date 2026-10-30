"""The mod builder on a synthetic game: a procedural class with two slots and a nested option, materials with textures,
gun and thruster locators; checks shipkits.json, ships.json, the GLB parts, the mounts and the maps. No game files."""
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
from fixtures import write  # noqa: E402
import build  # noqa: E402
import glb  # noqa: E402
from nms import hgpak  # noqa: E402

try:
    from compression import zstd  # noqa: F401
    HAVE_ZSTD = True
except ImportError:
    HAVE_ZSTD = False


def box(cx, cy, cz, s=0.5):
    p = np.array([[x, y, z] for x in (-s, s) for y in (-s, s) for z in (-s, s)], np.float32) + [cx, cy, cz]
    uv = np.zeros((8, 2), np.float32)
    n = p - [cx, cy, cz]
    n /= np.linalg.norm(n, axis=1)[:, None]
    idx = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]], np.uint32)
    return p, uv, n, idx


def synthetic_game(folder):
    """A 'fighter' class: _COCKPIT_ (A, B) and _WINGS_ (A with nested _ACC_ (none / B1)); the parts as referenced scenes."""
    files = {}
    tex = fixtures.make_dds_dxt1()
    files["textures/common/spacecraft/test/primary.dds"] = tex
    files["textures/common/spacecraft/test/primary.masks.dds"] = tex
    files["textures/common/spacecraft/test/primary.normal.dds"] = tex
    files["textures/common/spacecraft/test/glow.dds"] = tex
    files["models/common/spacecraft/fighters/parts/cockpita/primary.material.mbin"] = fixtures.make_material(
        "HQTrimPrimary_Mat", 45, "TEXTURES/COMMON/SPACECRAFT/TEST/PRIMARY.DDS", "TEXTURES/COMMON/SPACECRAFT/TEST/PRIMARY.MASKS.DDS",
        "TEXTURES/COMMON/SPACECRAFT/TEST/PRIMARY.NORMAL.DDS")
    files["models/common/spacecraft/fighters/parts/cockpita/glow.material.mbin"] = fixtures.make_material(
        "HQLight_Mat", 19, "TEXTURES/COMMON/SPACECRAFT/TEST/GLOW.DDS", colour=(0.2, 0.9, 1, 1))
    files["textures/effects/ship/engine_jet.dds"] = tex
    files["textures/common/spacecraft/shared/engineglow.1.dds"] = tex
    files["models/common/spacecraft/fighters/parts/cockpita/jet.material.mbin"] = fixtures.make_material(
        "EngineJet_Mat", 2, "TEXTURES/EFFECTS/SHIP/ENGINE_JET.DDS")
    files["models/common/spacecraft/fighters/parts/cockpita/engineglow.material.mbin"] = fixtures.make_material(
        "EngineGlow_Mat", 19, "TEXTURES/COMMON/SPACECRAFT/SHARED/ENGINEGLOW.1.DDS")

    def part(name, meshes, extra_children=(), material="primary", joint_meshes=(), folder="models/common/spacecraft/fighters/parts"):
        base = f"{folder}/{name}"
        g, d = fixtures.make_geometry(meshes)
        files[base + ".geometry.mbin.pc"] = g
        files[base + ".geometry.data.mbin.pc"] = d
        children = [{"name": mid.title(), "type": "MESH", "attrs": {"LODLEVEL": "0", "MATERIAL": f"MODELS\\COMMON\\SPACECRAFT\\FIGHTERS\\PARTS\\COCKPITA\\{material.upper()}.MATERIAL.MBIN"}}
                    for mid in meshes if not mid.endswith("LOD1") and mid not in joint_meshes]
        children.extend({"name": mid.title(), "type": "MESH", "attrs": {"LODLEVEL": "1", "MATERIAL": "MODELS\\COMMON\\SPACECRAFT\\FIGHTERS\\PARTS\\COCKPITA\\PRIMARY.MATERIAL.MBIN"}}
                        for mid in meshes if mid.endswith("LOD1"))
        children.extend(extra_children)
        files[base + ".scene.mbin"] = fixtures.make_scene({"name": base.upper().replace("/", "\\"), "type": "MODEL",
                                                           "attrs": {"GEOMETRY": base.upper().replace("/", "\\") + ".GEOMETRY.MBIN"}, "children": children})
        return base.upper().replace("/", "\\") + ".SCENE.MBIN"

    pos, uv, n, idx = box(0, 1, 2)
    detail = box(0, 1, 2, 0.1)
    cockpit_a = part("cockpita", {"COCKPITALOD0": (pos, uv, n, idx), "COCKPITALOD1": detail})
    cockpit_b = part("cockpitb", {"COCKPITBLOD0": box(0, 1, 2.5, 0.8)})
    # a thruster as the game builds it: the jet cone under Stage2 (pointing +Z here, turned around by the reference),
    # the glow disc under Stage1, a Trail locator sized by its scale
    jet_pos = np.array([[0, 0, 0], [0.3, 0, 0], [0, 0.3, 0], [0, 0, 2.0]], np.float32)
    jet = part("jet", {"JETLOD0": (jet_pos, np.zeros((4, 2), np.float32), np.array([[0, 0, 1]] * 4, np.float32), np.array([[0, 1, 2], [1, 3, 2]], np.uint32))},
               material="jet", joint_meshes={"JETLOD0"},
               extra_children=[{"name": "Stage2", "type": "LOCATOR", "children": [{"name": "JetLOD0", "type": "MESH", "attrs": {"LODLEVEL": "0", "MATERIAL": "MODELS\\COMMON\\SPACECRAFT\\FIGHTERS\\PARTS\\COCKPITA\\JET.MATERIAL.MBIN"}}]}])
    glow = part("glow", {"GLOWLOD0": box(0, 0, 0, 0.2)}, material="engineglow", joint_meshes={"GLOWLOD0"},
                extra_children=[{"name": "Stage1", "type": "LOCATOR", "children": [{"name": "GlowLOD0", "type": "MESH", "attrs": {"LODLEVEL": "0", "MATERIAL": "MODELS\\COMMON\\SPACECRAFT\\FIGHTERS\\PARTS\\COCKPITA\\ENGINEGLOW.MATERIAL.MBIN"}}]}])
    engine_children = [{"name": "RefEngine1", "type": "REFERENCE", "attrs": {"SCENEGRAPH": jet}, "transform": ((0, 180, 0), (1, 1, 1), (0.5, 1, -2)),
                        "children": [{"name": "Trail", "type": "LOCATOR", "transform": ((0, 0, 0), (0.75, 0.75, 0.75), (0, 0, 0.3))}]},
                       {"name": "RefEngine2", "type": "REFERENCE", "attrs": {"SCENEGRAPH": glow}, "transform": ((0, 180, 0), (1, 1, 1), (-0.5, 1, -2)),
                        "children": [{"name": "Trail", "type": "LOCATOR", "transform": ((0, 0, 0), (0.75, 0.75, 0.75), (0, 0, 0.3))}]},
                       {"name": "EngineLight", "type": "LIGHT", "attrs": {"COL_R": "0.600000", "COL_G": "0.100000", "COL_B": "1.000000"}}]
    files["models/common/spacecraft/fighters/parts/engine/entities/spin.entity.mbin"] = fixtures.make_entity(rotation=((0, 0, 1), 0.5))
    engine_children.append({"name": "TurbineLOD0", "type": "MESH", "attrs": {"LODLEVEL": "0", "ATTACHMENT": "MODELS\\COMMON\\SPACECRAFT\\FIGHTERS\\PARTS\\ENGINE\\ENTITIES\\SPIN.ENTITY.MBIN",
                                                                             "MATERIAL": "MODELS\\COMMON\\SPACECRAFT\\FIGHTERS\\PARTS\\COCKPITA\\PRIMARY.MATERIAL.MBIN"},
                            "transform": ((0, 0, 0), (1, 1, 1), (0, 1, -2.8))})
    engine = part("engine", {"ENGINELOD0": box(0, 1, -2, 0.7), "TURBINELOD0": box(0, 0, 0, 0.3)}, engine_children)
    gun = part("gun", {"GUNLOD0": box(0, 0, 0, 0.1)}, folder="models/common/spacecraft/shared/weapons")
    acc = part("acc", {"ACCLOD0": box(0, 2, 0, 0.3)})
    # the wings' flap: a joint with a mesh, an idle loop nodding it and a take-off swinging it 90 degrees for flight
    q90 = (0.0, 0.0, math.sin(math.radians(45)), math.cos(math.radians(45)))
    files["models/common/spacecraft/fighters/parts/wingsa/anims/idle.anim.mbin"] = fixtures.make_animation(
        [("FlapJNT", 0, 0, 0)], [{"rotations": [(0, 0, 0, 1)]}, {"rotations": [(0, 0, math.sin(0.1), math.cos(0.1))]}, {"rotations": [(0, 0, 0, 1)]}],
        {"scales": [(1, 1, 1)], "translations": [(3, 1, -1)]})
    files["models/common/spacecraft/fighters/parts/wingsa/anims/takeoff.anim.mbin"] = fixtures.make_animation(
        [("FlapJNT", 0, 0, 0)], [{"rotations": [(0, 0, 0, 1)]}, {"rotations": [q90]}], {"scales": [(1, 1, 1)], "translations": [(3, 1, -1)]})
    files["models/common/spacecraft/fighters/parts/wingsa/entities/wings.entity.mbin"] = fixtures.make_entity(
        anims=[("", "MODELS/COMMON/SPACECRAFT/FIGHTERS/PARTS/WINGSA/ANIMS/IDLE.ANIM.MBIN", 0),
               ("TAKEOFF", "MODELS/COMMON/SPACECRAFT/FIGHTERS/PARTS/WINGSA/ANIMS/TAKEOFF.ANIM.MBIN", 2)])
    wing_children = [{"name": "Data", "type": "LOCATOR", "attrs": {"ATTACHMENT": "MODELS\\COMMON\\SPACECRAFT\\FIGHTERS\\PARTS\\WINGSA\\ENTITIES\\WINGS.ENTITY.MBIN"}},
                     {"name": "FlapJNT", "type": "JOINT", "transform": ((0, 0, 0), (1, 1, 1), (3, 1, -1)),
                      "children": [{"name": "FlapLOD0", "type": "MESH", "attrs": {"LODLEVEL": "0", "MATERIAL": "MODELS\\COMMON\\SPACECRAFT\\FIGHTERS\\PARTS\\COCKPITA\\PRIMARY.MATERIAL.MBIN"}}]}]
    wings_a = part("wingsa", {"WINGSALOD0": (np.array([[-4, 1, 0], [4, 1, 0], [0, 1, -1], [0, 1.2, 0]], np.float32), np.zeros((4, 2), np.float32),
                                              np.array([[0, 1, 0]] * 4, np.float32), np.array([[0, 1, 2], [0, 3, 1]], np.uint32)),
                              "FLAPLOD0": box(1, 0, 0, 0.2)},
                   [{"name": "Gun1Ref", "type": "REFERENCE", "attrs": {"SCENEGRAPH": gun}, "transform": ((0, 0, 0), (1, 1, 1), (3, 1, 0))},
                    {"name": "Gun1Ref1", "type": "REFERENCE", "attrs": {"SCENEGRAPH": gun}, "transform": ((0, 0, 0), (1, 1, 1), (-3, 1, 0))},
                    {"name": "Contrail1", "type": "LOCATOR", "transform": ((0, 180, 0), (1, 1, 1), (-4, 1, -0.5))}] + wing_children, joint_meshes={"FLAPLOD0"})
    proc = "models/common/spacecraft/fighters/fighter_proc"
    files[proc + ".scene.mbin"] = fixtures.make_scene({
        "name": "MODELS\\COMMON\\SPACECRAFT\\FIGHTERS\\FIGHTER_PROC", "type": "MODEL", "attrs": {},
        "children": [{"name": "ProcRoot_StarShip", "type": "LOCATOR", "children": [
            {"name": "_Cockpit_A", "type": "REFERENCE", "attrs": {"SCENEGRAPH": cockpit_a}},
            {"name": "_Cockpit_B", "type": "REFERENCE", "attrs": {"SCENEGRAPH": cockpit_b}},
            {"name": "_Engine_A", "type": "REFERENCE", "attrs": {"SCENEGRAPH": engine}},
            {"name": "_Wings_A", "type": "REFERENCE", "attrs": {"SCENEGRAPH": wings_a}, "transform": ((0, 0, 0), (1, 1, 1), (0, 0, -1)),
             "children": [{"name": "_Acc_B1", "type": "REFERENCE", "attrs": {"SCENEGRAPH": acc}, "transform": ((0, 0, 90), (1, 1, 1), (1, 0, 0))}]},
        ]}]})
    files[proc + ".descriptor.mbin"] = fixtures.make_descriptor([
        {"type": "_COCKPIT_", "options": [{"id": "_COCKPIT_A", "name": "_Cockpit_A", "chance": 0.3}, {"id": "_COCKPIT_B", "name": "_Cockpit_B", "chance": 0.7}]},
        {"type": "_ENGINE_", "options": [{"id": "_ENGINE_A", "name": "_Engine_A"}]},
        {"type": "_WINGS_", "options": [{"id": "_WINGS_A", "name": "_Wings_A", "groups": [
            {"type": "_ACC_", "options": [{"id": "_ACC_NONE1", "name": "_Acc_None1", "chance": 0.6}, {"id": "_ACC_B1", "name": "_Acc_B1", "chance": 0.4}]}]}]}])
    pc = os.path.join(folder, "GAMEDATA", "PCBANKS")
    os.makedirs(pc)
    half = len(files) // 2
    items = list(files.items())
    write(os.path.join(pc, "NMSARC.MeshCommon.pak"), fixtures.make_hgpak(dict(items[:half])))
    write(os.path.join(pc, "NMSARC.Misc.pak"), fixtures.make_hgpak(dict(items[half:])))
    return pc


def mats_of(kit):
    return kit["materials"]


def ship_of(ships, kit_id):
    return next(s for s in ships if s["id"] == kit_id)


@unittest.skipUnless(HAVE_ZSTD, "no zstd")
class BuildTests(unittest.TestCase):
    def test_fighter_kit(self):
        with tempfile.TemporaryDirectory() as d:
            pc = synthetic_game(d)
            out = os.path.join(d, "nms_ships")
            banks = hgpak.Banks(pc)
            kits, ships, report = build.build(banks, out, ["fighter"])
            self.assertEqual([w for w in report.warnings], [])
            self.assertEqual(len(kits), 1)
            kit = kits[0]
            self.assertEqual(kit["id"], "fighter")
            self.assertEqual(kit["slots"], ["cockpit", "engine", "wings"])
            ids = [p["id"] for p in kit["parts"]]
            self.assertEqual(ids, ["fighter-cockpit_a", "fighter-cockpit_b", "fighter-engine_a", "fighter-wings_a", "fighter-wings_a_acc_b1"])
            by_id = {p["id"]: p for p in kit["parts"]}
            self.assertEqual(by_id["fighter-wings_a_acc_b1"]["name"], "Wings A (Acc B1)")
            # mounts: the wings' two guns, the engine's two thruster trails with the light's colour, in game units (scale 4 x 20)
            guns = [m for m in by_id["fighter-wings_a"]["mounts"] if m["slotType"] == 0]
            self.assertEqual(len(guns), 2)
            self.assertEqual(guns[0]["position_engine"], [240.0, 80.0, -80.0])
            missiles = [m for m in by_id["fighter-wings_a"]["mounts"] if m["slotType"] == 1]
            self.assertEqual([m["position_engine"] for m in missiles], [m["position_engine"] for m in guns])   # rockets leave the same points
            exhausts = [m for m in by_id["fighter-engine_a"]["mounts"] if m["slotType"] == 3]
            self.assertEqual(len(exhausts), 2)
            self.assertEqual(exhausts[0]["position_engine"], [40.0, 80.0, -184.0])   # the trail 0.3 behind the turned-around thruster
            self.assertEqual(exhausts[0]["glowColor"], [0.6, 0.1, 1.0])
            self.assertEqual(exhausts[0]["socketScale"], 1.5)   # the trail locator's scale 0.75 x the kit scale 4 / 2
            boosters = [m for m in by_id["fighter-wings_a"]["mounts"] if m["slotType"] == 5]
            self.assertEqual(len(boosters), 1)   # the wings' contrail
            self.assertEqual(boosters[0]["position_engine"], [-320.0, 80.0, -120.0])
            self.assertEqual(boosters[0]["socketScale"], 0.5)
            self.assertNotIn("mounts", by_id["fighter-cockpit_a"])
            # stat bonuses from size: cockpit B is the bigger box, so it gives hull and cargo and costs acceleration; A the reverse
            self.assertGreater(by_id["fighter-cockpit_b"]["stats"]["armor"], 0)
            self.assertLess(by_id["fighter-cockpit_a"]["stats"]["armor"], 0)
            self.assertLess(by_id["fighter-cockpit_b"]["stats"]["acceleration"], 0)
            self.assertTrue(all(abs(v) <= build.STAT_LIMIT for p in kit["parts"] for v in p.get("stats", {}).values()))
            self.assertNotIn("stats", by_id["fighter-engine_a"])   # alone in its slot: nothing to compare with
            # the GLBs: the cockpit's LOD0 box only (its coarser LOD1 left out), the acc variant holds the turned accessory
            doc, binary = glb.read(os.path.join(out, by_id["fighter-cockpit_a"]["model"]))
            self.assertEqual(len(doc["meshes"]), 1)
            self.assertEqual(doc["accessors"][doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]["count"], 8)
            self.assertEqual(doc["materials"][0]["name"], "mat_0000_paint1")
            doc, _ = glb.read(os.path.join(out, by_id["fighter-wings_a_acc_b1"]["model"]))
            names = [m["name"] for m in doc["meshes"]]
            self.assertTrue(any("Acclod0" in n for n in names), names)
            self.assertTrue(any("Gunlod0" in n for n in names), names)   # the ship gun is a fixed part of the hull
            acc = next(doc["accessors"][p["primitives"][0]["attributes"]["POSITION"]] for p in doc["meshes"] if "Acclod0" in p["name"])
            self.assertAlmostEqual(acc["max"][0], -0.7, places=2)   # the accessory box at (0, 2, 0) +- 0.3 turned 90 about Z (x = -2) and moved by its node (1, 0, 0)
            doc, _ = glb.read(os.path.join(out, by_id["fighter-wings_a"]["model"]))
            self.assertFalse(any("Acclod0" in m["name"] for m in doc["meshes"]))
            # the engine part: the jet cone is a flame card (u 0 at the nozzle, 1 at the tip, a main card), the glow disc
            # an engine-lit glow, both in the engine light's colour; its turbine spins: a 2 s rotation loop (0.5 turns per
            # second) about the mesh's own Z, the mesh under a node at its place
            doc, binary = glb.read(os.path.join(out, by_id["fighter-engine_a"]["model"]))
            jet = next(m for m in doc["meshes"] if "JetLOD0" in m["name"])
            prim = jet["primitives"][0]
            self.assertTrue(doc["materials"][prim["material"]]["name"].endswith("_flame"))
            acc = doc["accessors"]
            def read(ai, dtype, n):
                a = acc[ai]; v = doc["bufferViews"][a["bufferView"]]
                return np.frombuffer(binary, dtype=dtype, count=a["count"] * n, offset=v["byteOffset"]).reshape(a["count"], n)
            uv = read(prim["attributes"]["TEXCOORD_0"], "<f4", 2)
            pos = read(prim["attributes"]["POSITION"], "<f4", 3)
            self.assertAlmostEqual(float(uv[:, 0].min()), 0.0, places=5)
            self.assertAlmostEqual(float(uv[:, 0].max()), 1.0, places=5)
            self.assertEqual(int(np.argmax(uv[:, 0])), int(np.argmin(pos[:, 2])))   # the tip is the rearmost point
            self.assertEqual(set(read(prim["attributes"]["TEXCOORD_1"], "<f4", 2)[:, 1].tolist()), {0.5})
            flame = next(m for m in mats_of(kit) if m["material"].endswith("_flame"))
            self.assertTrue(flame["flame"])
            self.assertEqual(flame["emissionColor"], [0.6, 0.1, 1.0])
            self.assertEqual(flame["flameNoise"], "maps/engine_jet_noise.png")
            self.assertTrue(os.path.exists(os.path.join(out, flame["flameNoise"])))
            glow = next(m for m in mats_of(kit) if m["material"].endswith("_engineglow"))
            self.assertTrue(glow["engine"])
            self.assertEqual(glow["engineIdle"], 1)
            self.assertEqual(glow["emissionColor"], [0.6, 0.1, 1.0])
            self.assertTrue(os.path.exists(os.path.join(out, glow["emission"])))
            self.assertFalse(any(m["name"].endswith("_lights") for m in doc["materials"]))
            self.assertEqual(ship_of(ships, "fighter")["engineGlowColor"], [0.6, 0.1, 1.0])
            self.assertEqual([a["name"] for a in doc["animations"]], ["flight"])
            chan = doc["animations"][0]["channels"][0]
            self.assertEqual(chan["target"]["path"], "rotation")
            turbine = doc["nodes"][chan["target"]["node"]]
            self.assertTrue(turbine["name"].endswith("TurbineLOD0"))
            np.testing.assert_allclose(turbine["translation"], [0.0, 1.0, -2.8], atol=1e-5)
            times = doc["accessors"][doc["animations"][0]["samplers"][0]["input"]]
            self.assertAlmostEqual(times["max"][0], 2.0, places=5)
            # the wings' flap: posed for flight (its take-off's last frame, 90 degrees about Z) and nodding in the loop
            doc, _ = glb.read(os.path.join(out, by_id["fighter-wings_a"]["model"]))
            flap = next(n for n in doc["nodes"] if n["name"] == "FlapJNT")
            self.assertAlmostEqual(flap["rotation"][2], math.sin(math.radians(45)), places=3)
            np.testing.assert_allclose(flap["translation"], [3.0, 1.0, -1.0], atol=1e-5)
            self.assertEqual([a["name"] for a in doc["animations"]], ["flight", "takeoff"])   # the loop first (the remake plays it), the take-off kept after it
            self.assertEqual(doc["animations"][0]["channels"][0]["target"]["node"], doc["nodes"].index(flap))
            self.assertAlmostEqual(doc["accessors"][doc["animations"][0]["samplers"][0]["input"]]["max"][0], 2 / 30, places=5)
            mesh_node = next(n for n in doc["nodes"] if n["name"].endswith("FlapLOD0"))
            self.assertIn(doc["nodes"].index(mesh_node), flap["children"])
            # materials and maps
            mats = {m["material"]: m for m in kit["materials"]}
            self.assertEqual(mats["mat_0000_paint1"]["diffuse"], "maps/test_primary_d.png")
            self.assertEqual(mats["mat_0000_paint1"]["metallicSmoothness"], "maps/test_primary_masks_ms.png")
            self.assertEqual(mats["mat_0000_paint1"]["normal"], "maps/test_primary_normal_n.png")
            for m in mats.values():
                for k in ("diffuse", "normal", "metallicSmoothness", "emission"):
                    if k in m:
                        self.assertTrue(os.path.exists(os.path.join(out, m[k])), m[k])
            self.assertTrue(all(s["id"] in ("paint1", "paint2", "paint3", "lights", "engines") for s in kit["colorSlots"]))
            # the ship
            self.assertEqual(len(ships), 1)
            ship = ships[0]
            self.assertEqual(ship["kit"], "fighter")
            self.assertEqual(ship["build"]["cockpit"], "fighter-cockpit_a")
            self.assertEqual(ship["build"]["wings"], "fighter-wings_a")
            self.assertEqual(ship["slots"]["primary"], 2)
            mod = json.load(open(os.path.join(out, "mod.json")))
            self.assertEqual(mod["id"], "nms_ships")
            self.assertEqual(json.load(open(os.path.join(out, "shipkits.json")))[0]["id"], "fighter")

    def test_hull_kits_per_option(self):
        """A class whose one group holds whole hulls with nested groups becomes a kit per hull."""
        d = fixtures.make_descriptor([{"type": "_SHIP_", "options": [
            {"id": "_SHIP_ROY", "name": "_Ship_Royal", "groups": [{"type": "_WINGS_", "options": [{"id": "_WINGS_A", "name": "_Wings_A"}, {"id": "_WINGS_B", "name": "_Wings_B"}]}]},
            {"id": "_SHIP_SQU", "name": "_Ship_Squid"}]}])
        from nms import descriptors
        desc = descriptors.Descriptor(d)
        kb = build.KitBuilder(None, "/nonexistent", build.Report())
        kits = []
        kb.expand("exotic", "Exotic", [], desc.groups, kits, "x.scene.mbin", desc)
        self.assertEqual([(k[0], k[1], k[2]) for k in kits], [("exotic-roy", "Exotic Royal", ["ship", "wings"]), ("exotic-squ", "Exotic Squid", ["ship"])])
        roy_parts = kits[0][3]
        self.assertEqual([p.id for p in roy_parts], ["exotic_roy-hull", "exotic_roy-wings_a", "exotic_roy-wings_b"])
        self.assertEqual(roy_parts[0].picks, {"_ship_roy"})
        self.assertEqual(roy_parts[1].within, "_Ship_Royal")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_ZSTD, "no zstd")
class FixedDesignTests(unittest.TestCase):
    def test_fixed_design_is_a_one_part_kit(self):
        """A class given by a scene (no procedural descriptor) becomes a kit of one hull part and a ship built from it."""
        with tempfile.TemporaryDirectory() as d:
            pc = synthetic_game(d)
            out = os.path.join(d, "nms_ships")
            banks = hgpak.Banks(pc)
            build.CLASSES["test_fixed"] = dict(scene="fighters/parts/cockpita", name="Test Fixed", scale=4.0, armor=300, cargo=30, handling=150,
                                               price=1000000, equipment=8, description="A fixed hull.")
            try:
                kits, ships, report = build.build(banks, out, ["test_fixed"])
            finally:
                del build.CLASSES["test_fixed"]
            self.assertEqual(report.warnings, [])
            self.assertEqual(len(kits), 1)
            kit = kits[0]
            self.assertEqual(kit["slots"], ["hull"])
            self.assertEqual([p["id"] for p in kit["parts"]], ["test_fixed-hull"])
            self.assertNotIn("stats", kit["parts"][0])
            doc, _ = glb.read(os.path.join(out, kit["parts"][0]["model"]))
            self.assertEqual(len(doc["meshes"]), 1)   # the cockpit's LOD0 only
            ship = ships[0]
            self.assertEqual(ship["kit"], "test_fixed")
            self.assertEqual(ship["build"]["hull"], "test_fixed-hull")
            self.assertEqual(ship["dealer"]["chance"], 1)   # a unique: rare at the dealers
