"""MBIN decoding (scenes, descriptors, geometry, materials) and the geometry maths, on files written by the fixtures."""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import fixtures  # noqa: E402
from nms import descriptors, geometry, mbin  # noqa: E402


class SceneTests(unittest.TestCase):
    def test_scene_tree(self):
        data = fixtures.make_scene({"name": "MODELS\\X\\PROC", "type": "MODEL", "attrs": {"GEOMETRY": "MODELS\\X\\PROC.GEOMETRY.MBIN", "NUMLODS": "1"},
                                    "children": [{"name": "_Wings_A", "type": "REFERENCE", "attrs": {"SCENEGRAPH": "MODELS\\X\\WINGS_A.SCENE.MBIN"},
                                                  "transform": ((0, 180, 0), (1, 1, 1), (1.5, 0, -2))},
                                                 {"name": "Body", "type": "MESH", "attrs": {"LODLEVEL": "0", "MATERIAL": "MODELS\\X\\BODY.MATERIAL.MBIN"}}]})
        h = mbin.header(data)
        self.assertEqual(h["version"], 3300)
        name, root = mbin.load(data)
        self.assertEqual(name, "TkSceneNodeData")
        self.assertEqual(root["name"], "MODELS\\X\\PROC")
        self.assertEqual(root["type"], "MODEL")
        self.assertEqual(mbin.attributes(root)["NUMLODS"], "1")
        self.assertEqual(len(root["children"]), 2)
        wings = root["children"][0]
        self.assertEqual(wings["type"], "REFERENCE")
        self.assertEqual(wings["transform"], {"rot": [0, 180, 0], "scale": [1, 1, 1], "trans": [1.5, 0, -2]})
        self.assertEqual(mbin.attributes(wings)["SCENEGRAPH"], "MODELS\\X\\WINGS_A.SCENE.MBIN")
        with self.assertRaises(mbin.MBINError):
            mbin.load(data, "TkGeometryData")
        with self.assertRaises(mbin.MBINError):
            mbin.load(b"\0" * 64)

    def test_descriptor_tree_and_picks(self):
        data = fixtures.make_descriptor([
            {"type": "_WINGS_", "options": [
                {"id": "_WINGS_A", "name": "_Wings_A", "chance": 0.2, "refs": ["MODELS/X/WINGS_A.SCENE.MBIN"],
                 "groups": [{"type": "_ACC_", "options": [{"id": "_ACC_NONE1", "name": "_Acc_None1"}, {"id": "_ACC_B1", "name": "_Acc_B1", "chance": 0.5}]}]},
                {"id": "_WINGS_B", "name": "_Wings_B", "chance": 0.8}]},
            {"type": "_ENGINE_", "options": [{"id": "_ENGINE_A", "name": "_Engine_A"}]}])
        d = descriptors.Descriptor(data)
        self.assertEqual([g.slot for g in d.groups], ["wings", "engine"])
        wings = d.groups[0]
        self.assertEqual([o.id for o in wings.options], ["_WINGS_A", "_WINGS_B"])
        a = wings.options[0]
        self.assertEqual(a.references, ["MODELS/X/WINGS_A.SCENE.MBIN"])
        self.assertAlmostEqual(a.chance, 0.2, places=5)
        self.assertEqual([g.type_id for g in a.groups], ["_ACC_"])
        self.assertTrue(a.groups[0].options[0].is_none)
        self.assertEqual(a.groups[0].depth, 1)
        self.assertEqual(descriptors.likeliest(wings).id, "_WINGS_B")
        picks = set()
        for g in d.groups:
            descriptors.default_picks(g, picks)
        self.assertEqual(picks, {"_wings_b", "_engine_a"})
        self.assertEqual(descriptors.default_picks(wings.options[0].groups[0]), {"_acc_none1"})   # the none is likelier: nothing shows
        choose = descriptors.chooser(d, {"_wings_a", "_acc_b1"})

        class N:
            def __init__(self, name):
                self.name = name
        self.assertTrue(choose(N("_Wings_A")))
        self.assertFalse(choose(N("_Wings_B")))
        self.assertTrue(choose(N("_Acc_B1")))
        self.assertFalse(choose(N("_Acc_None1")))
        self.assertTrue(choose(N("SomeMesh")))
        self.assertEqual(d.option_names, {"_wings_a", "_wings_b", "_acc_none1", "_acc_b1", "_engine_a"})

    def test_material(self):
        data = fixtures.make_material("Primary_Mat", material_class=45, diffuse="TEXTURES/X/P.BASE.DDS", masks="TEXTURES/X/P.MASKS.DDS",
                                      normal="TEXTURES/X/P.NORMAL.DDS", colour=(0.5, 0.25, 1, 1), flags=(0, 2, 52))
        name, m = mbin.load(data, "TkMaterialData")
        self.assertEqual(m["name"], "Primary_Mat")
        self.assertEqual(m["material_class"], 45)
        self.assertEqual(m["flags"], [0, 2, 52])
        self.assertEqual([(s["name"], s["map"]) for s in m["samplers"]],
                         [("gDiffuseMap", "TEXTURES/X/P.BASE.DDS"), ("gMasksMap", "TEXTURES/X/P.MASKS.DDS"), ("gNormalMap", "TEXTURES/X/P.NORMAL.DDS")])
        self.assertEqual(m["uniforms"][0]["name"], "gMaterialColourVec4")
        self.assertEqual([round(v, 3) for v in m["uniforms"][0]["values"]], [0.5, 0.25, 1, 1])


class GeometryTests(unittest.TestCase):
    def test_mesh_streams(self):
        pos = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1.5]], np.float32)
        uv = np.array([[0, 0], [1, 0], [0, 1], [1, 1]], np.float32)
        nrm = np.array([[0, 0, 1], [0, 1, 0], [1, 0, 0], [0, -1, 0]], np.float32)
        idx = np.array([[0, 1, 2], [0, 2, 3]], np.uint32)
        gdata, ddata = fixtures.make_geometry({"BODYLOD0": (pos, uv, nrm, idx)})
        self.assertEqual(mbin.header(gdata)["magic"], mbin.MAGIC_GEOMETRY)
        g = geometry.Geometry(gdata, ddata)
        self.assertEqual(g.mesh_ids, ["BODYLOD0"])
        self.assertTrue(g.has("BodyLOD0"))
        m = g.mesh("BodyLOD0")
        np.testing.assert_allclose(m.positions, pos, atol=1e-3)
        np.testing.assert_allclose(m.uvs, uv, atol=1e-3)
        np.testing.assert_allclose(m.normals, nrm, atol=3e-3)
        np.testing.assert_array_equal(m.indices, idx)
        self.assertEqual(m.triangle_count, 2)
        with self.assertRaises(KeyError):
            g.mesh("nothing")

    def test_octahedral_roundtrip(self):
        rng = np.random.default_rng(1)
        v = rng.normal(size=(200, 3))
        v /= np.linalg.norm(v, axis=1)[:, None]
        words = np.array([fixtures.octa_encode(x) for x in v], np.uint32)
        back = geometry.unpack_normals(words)
        self.assertLess(np.abs(back - v).max(), 0.01)

    def test_transform_order(self):
        # the rotations apply Z, then X, then Y: a point on +X turned 90 about Z goes to +Y, then 90 about X takes +Y to +Z
        M = geometry.transform_matrix({"rot": [90, 0, 90], "scale": [1, 1, 1], "trans": [0, 0, 0]})
        p = geometry.apply(M, np.array([[1, 0, 0]], np.float32))[0]
        np.testing.assert_allclose(p, [0, 0, 1], atol=1e-6)
        M = geometry.transform_matrix({"rot": [0, 180, 0], "scale": [2, 2, 2], "trans": [1, 2, 3]})
        p = geometry.apply(M, np.array([[0, 0, 1]], np.float32))[0]
        np.testing.assert_allclose(p, [1, 2, 1], atol=1e-5)
        n = geometry.apply_normals(M, np.array([[0, 0, 1]], np.float32))[0]
        np.testing.assert_allclose(n, [0, 0, -1], atol=1e-6)

    def test_face_normals(self):
        pos = np.array([[0, 0, 0], [1, 0, 0], [0, 0, -1]], np.float32)
        n = geometry.face_normals(pos, np.array([[0, 1, 2]], np.uint32))
        np.testing.assert_allclose(n, [[0, 1, 0]] * 3, atol=1e-6)


if __name__ == "__main__":
    unittest.main()


class AnimationTests(unittest.TestCase):
    def test_animation_file(self):
        from nms import animation
        import math
        q = (0.0, math.sin(math.radians(30)), 0.0, math.cos(math.radians(30)))
        frames = [{"rotations": [(0, 0, 0, 1)], "translations": [(0, 0, 0)]}, {"rotations": [q], "translations": [(1, 2, 3)]}]
        still = {"rotations": [(0, 0, 0, 1)], "scales": [(1, 1, 1), (2, 2, 2)], "translations": [(5, 0, 0)]}
        data = fixtures.make_animation([("WingJNT", 0, 1, 0), ("StaticJNT", 1, 0, 1)], frames, still)
        an = animation.Animation(data)
        self.assertEqual(an.nodes, ["WingJNT", "StaticJNT"])
        self.assertEqual(an.frame_count, 2)
        self.assertEqual(an.animated("WingJNT"), (True, False, True))
        self.assertEqual(an.animated("StaticJNT"), (False, False, False))
        track = an.track("WingJNT")
        self.assertEqual(len(track), 2)
        rot, sc, tr = track[1]
        self.assertAlmostEqual(rot[1], q[1], places=3)
        self.assertAlmostEqual(rot[3], q[3], places=3)
        self.assertEqual(sc, (2, 2, 2))
        self.assertEqual(tr, (1, 2, 3))
        rot, sc, tr = an.track("StaticJNT")[0]
        self.assertEqual(rot, (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(tr, (5, 0, 0))
        self.assertIsNone(an.track("nothing"))

    def test_entity_components(self):
        from nms import animation
        data = fixtures.make_entity(anims=[("", "MODELS/X/ANIMS/X_IDLE.ANIM.MBIN", 0), ("TAKEOFF", "MODELS/X/ANIMS/X_TAKEOFF.ANIM.MBIN", 2),
                                           ("GEARUP", "MODELS/X/ANIMS/GEAR.ANIM.MBIN", 0)], rotation=((0, 1, 0), 0.5))
        comps = animation.entity_components(data)
        rot = comps[animation.HASH_ROTATION_COMPONENT]
        self.assertEqual(rot["axis"], [0, 1, 0])
        self.assertAlmostEqual(rot["speed"], 0.5)
        comp = comps[animation.HASH_ANIMATION_COMPONENT]
        self.assertEqual(comp["idle"]["filename"], "MODELS/X/ANIMS/X_IDLE.ANIM.MBIN")
        self.assertEqual([a["anim"] for a in comp["anims"]], ["TAKEOFF", "GEARUP"])
        self.assertEqual(animation.flight_loop(comp)["filename"], "MODELS/X/ANIMS/X_IDLE.ANIM.MBIN")
        self.assertEqual(animation.transition(comp, "takeoff")["anim"], "TAKEOFF")
        self.assertIsNone(animation.transition(comp, "LANDING"))
        gear_only = fixtures.make_entity(anims=[("GEARUP", "MODELS/X/ANIMS/GEAR.ANIM.MBIN", 0)])
        self.assertIsNone(animation.flight_loop(animation.entity_components(gear_only)[animation.HASH_ANIMATION_COMPONENT]))


class IosAnimationTests(unittest.TestCase):
    def test_ios_layout_half_floats_and_half_rate(self):
        """The iOS game's animation files keep the vectors as half floats and the longer ones every other frame:
        the values read the same, and resampled to 30 frames a second the track gets a blended frame between each two."""
        from nms import animation
        frames = [{"rotations": [(0, 0, 0, 1)], "translations": [(0, 0, 0)]}, {"rotations": [(0, 0, 0, 1)], "translations": [(2, 4, 6)]}]
        still = {"rotations": [(0, 0, 0, 1)], "scales": [(1, 1, 1)], "translations": [(5, 0, 0)]}
        an = animation.Animation(fixtures.make_animation([("WingJNT", 0, 0, 0)], frames, still, ios=True))
        self.assertTrue(an.half_rate)
        self.assertEqual(an.fps, 15)
        self.assertEqual(an.still["translations"], [(5.0, 0.0, 0.0)])
        self.assertEqual(an.still["scales"], [(1.0, 1.0, 1.0)])
        self.assertEqual(an.track("WingJNT")[1][2], (2.0, 4.0, 6.0))
        track = an.track_at("WingJNT", 30)
        self.assertEqual(len(track), 3)
        self.assertEqual(track[1][2], (1.0, 2.0, 3.0))
        pc = animation.Animation(fixtures.make_animation([("WingJNT", 0, 0, 0)], frames, still))
        self.assertEqual(pc.fps, 30)
        self.assertEqual(len(pc.track_at("WingJNT", 30)), 2)
