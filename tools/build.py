"""Builds the nms_ships mod: customizable ship kits from No Man's Sky's starship classes, out of the game's own archives.

A class's procedural descriptor is a tree of groups (the choices) and options. A class whose groups sit side by side
(the fighter: cockpit, engine, wings) is one kit with those groups as slots and their options as parts. A class that
begins with one group of whole hulls (the explorer, shuttle, exotic: `_COCKPIT_` A / B, `_SHUTTLE_` A / B ...) is one
kit per hull, the hull itself a part of its own slot and the groups nested under it the kit's other slots. Deeper
nesting is baked into variants of a part (`wings_f`, `wings_f-acc_a3`), a few per part. A part's GLB is its option's
subtree of the procedural scene resolved through its references, with each part scene's own optional details picked by
its descriptor (the likeliest option), all in the ship's frame, metres, nose along +Z. Materials are shared across the
mod by their texture set, NMS's primary / secondary / tertiary paint materials exposed as colour slots; weapon mounts
come from the parts' gun references, exhausts from their thruster trails; each kit is one ship in ships.json with its
default build.
"""
import json
import os
import re
import shutil
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from nms import descriptors, geometry, hgpak, mbin, scene, textures   # noqa: E402
import glb   # noqa: E402

MOD_ID = "nms_ships"
VERSION = "0.1"
UNITS_PER_METRE = 20.0          # the remake's game units
MAX_VARIANTS = 4                # variants of one option over its nested groups
MAX_PARTS_PER_SLOT = 14
MAX_TEXTURE = 2048

SPACECRAFT = "models/common/spacecraft/"
CLASSES = {
    "fighter": dict(proc="fighters/fighter_proc", name="Fighter", scale=4.0, armor=260, cargo=30, handling=160, price=1400000,
                    equipment=9, description="A No Man's Sky fighter: fast, armed, little room for cargo. Customize it in the hangar."),
    "hauler": dict(proc="dropships/dropship_proc", name="Hauler", scale=2.8, armor=380, cargo=110, handling=90, price=2600000,
                   equipment=11, description="A No Man's Sky hauler: a big hold and a thick hull, slow to turn. Customize it in the hangar."),
    "explorer": dict(proc="scientific/scientific_proc", name="Explorer", scale=3.5, armor=240, cargo=55, handling=140, price=1900000,
                     equipment=12, description="A No Man's Sky explorer: light, far-ranging, room for equipment. Customize it in the hangar."),
    "shuttle": dict(proc="shuttle/shuttle_proc", name="Shuttle", scale=3.2, armor=200, cargo=60, handling=120, price=900000,
                    equipment=8, description="A No Man's Sky shuttle: cheap and plain, a little of everything. Customize it in the hangar."),
    "exotic": dict(proc="s-class/s-class_proc", name="Exotic", scale=4.0, armor=300, cargo=45, handling=175, price=4800000,
                   equipment=12, description="A No Man's Sky exotic: a rare S-class hull, the best handling there is. Customize it in the hangar."),
    "solar": dict(proc="sailship/sailship_proc", name="Solar", scale=3.6, armor=220, cargo=50, handling=150, price=2400000,
                  equipment=10, description="A No Man's Sky solar ship: sails for the sun's wind. Customize it in the hangar."),
    "sentinel": dict(proc="sentinelship/sentinelship_proc", name="Sentinel Interceptor", scale=4.0, armor=420, cargo=40, handling=165,
                     price=6900000, equipment=12, description="A No Man's Sky sentinel interceptor: a machine hull. Customize it in the hangar."),
}
SKIP_MATERIAL_CLASSES = {2, 12, 22, 24}   # Additive (engine jets: the remake draws its own flames), Decal, GunAdditive, GunGlow
EMISSIVE_CLASSES = {18, 19}               # Glow, GlowTranslucent
TRANSLUCENT_CLASSES = {62, 63, 15}        # Translucent, TranslucentPostScene, DoubleSided
SKIP_NODES = re.compile(r"(landinggear|landing_gear|frontpad|leftpad|rightpad|backpad|_gear\b|shadowmesh)", re.I)

PALETTE = [("white", "Snow White", "#F2F2F2"), ("silver", "Silver", "#B8BCC2", 0.9, 0.7), ("grey", "Graphite", "#5A5E63"),
           ("black", "Jet", "#1E1E22"), ("red", "Vermilion", "#C8321E"), ("orange", "Amber", "#E07B1A"),
           ("yellow", "Sulphur", "#E2C33A"), ("green", "Verdant", "#3E9B4B"), ("teal", "Teal", "#2E9C9A"),
           ("blue", "Cobalt", "#2A5DC8"), ("purple", "Violet", "#7A3FB8"), ("pink", "Magenta", "#C83C9B"),
           ("brown", "Rust", "#7A4A2A"), ("gold", "Gold", "#C9A227", 1.0, 0.75)]
LIGHTS = [("white", "White", "#FFFFFF"), ("cyan", "Cyan", "#49D6FF"), ("amber", "Amber", "#FFB347"), ("red", "Red", "#FF4A3A"),
          ("green", "Green", "#4AFF7A"), ("violet", "Violet", "#B06CFF"), ("blue", "Blue", "#4A6AFF")]
DEFAULT_COLORS = {"paint1": "white", "paint2": "grey", "paint3": "orange", "lights": "cyan", "engines": "violet"}


def log(msg):
    print(msg, flush=True)


class Report:
    def __init__(self):
        self.warnings = []
        self.notes = []
        self.missing_textures = []

    def warn(self, msg):
        self.warnings.append(msg)
        log("  ! " + msg)

    def note(self, msg):
        self.notes.append(msg)


# --- materials and textures ---------------------------------------------------------------------------------------

def role_of(material_name, mat):
    n = material_name.lower()
    if "primary" in n:
        return "paint1"
    if "secondary" in n:
        return "paint2"
    if "tertiary" in n:
        return "paint3"
    if mat and mat["material_class"] in EMISSIVE_CLASSES or "light" in n or "glow" in n:
        return "lights"
    if "trans" in n or "glass" in n:
        return "glass"
    return "plain"


def uniform(mat, name, default=(1, 1, 1, 1)):
    for u in mat["uniforms"]:
        if u["name"] == name:
            return u["values"]
    return list(default)


class Materials:
    """The mod's materials, one per distinct (maps, class, colour): `name_for(placed)` gives the GLB material name and
    adds the entry; `convert(out)` writes the PNGs."""

    def __init__(self, banks, report):
        self.banks = banks
        self.report = report
        self.cache = {}
        self.entries = {}      # key -> entry dict
        self.names = {}        # key -> material name
        self.textures = {}     # game path -> (png relative path, kind)

    def texture(self, game_path, kind):
        p = scene.game_path(game_path)
        if p in self.textures:
            return self.textures[p][0]
        if not self.banks.exists(p):
            self.report.missing_textures.append(p)
            self.textures[p] = (None, kind)
            return None
        stem = re.sub(r"[^a-z0-9]+", "_", p.replace("textures/common/spacecraft/", "").replace("textures/", "").rsplit(".", 1)[0]).strip("_")
        rel = f"maps/{stem}_{kind}.png"
        self.textures[p] = (rel, kind)
        return rel

    def name_for(self, placed):
        """(GLB material name, NMS material class) of a placed mesh's material."""
        path, mat = scene.material_of(self.banks, placed, self.cache)
        if mat is None:
            key, role, maps, colour, cls, nms_name = ("none",), "plain", {}, (1.0, 1.0, 1.0, 1.0), 45, "none"
        else:
            nms_name = mat["name"]
            cls = mat["material_class"]
            role = role_of(nms_name, mat)
            maps = {}
            for s in mat["samplers"]:
                n = s["name"].lower()
                if n == "gdiffusemap":
                    maps["diffuse"] = s["map"]
                elif n == "gmasksmap":
                    maps["masks"] = s["map"]
                elif n == "gnormalmap":
                    maps["normal"] = s["map"]
            colour = tuple(round(float(x), 3) for x in uniform(mat, "gMaterialColourVec4"))
            key = (tuple(sorted((k, scene.game_path(v)) for k, v in maps.items())), cls, colour, role)
        if key in self.names:
            return self.names[key], cls
        index = len(self.names)
        name = f"mat_{index:04d}_{role}"
        self.names[key] = name
        entry = {"material": name, "_nms": nms_name}
        for k, kind, field in (("diffuse", "d", "diffuse"), ("masks", "ms", "metallicSmoothness"), ("normal", "n", "normal")):
            if k in maps:
                rel = self.texture(maps[k], kind)
                if rel:
                    entry[field] = rel
        if cls in EMISSIVE_CLASSES or role == "lights":
            if entry.get("diffuse"):
                entry["emission"] = entry["diffuse"]
            entry["emissionColor"] = [round(float(x), 3) for x in colour[:3]]
            entry["emissionIntensity"] = 3
        if colour[:3] != (1.0, 1.0, 1.0) and role in ("plain", "glass"):
            entry["color"] = [round(float(x), 3) for x in colour[:3]]
        if cls in TRANSLUCENT_CLASSES or role == "glass":
            entry["opacity"] = 0.45
        if cls == 15:
            entry["doubleSided"] = True
        self.entries[key] = entry
        return name, cls

    def kit_entries(self):
        out = []
        for e in self.entries.values():
            if any(k in e for k in ("diffuse", "normal", "metallicSmoothness", "emissionColor", "color", "opacity")):
                out.append({k: v for k, v in e.items() if not k.startswith("_")})
        return out

    def convert(self, out, max_size=MAX_TEXTURE):
        done, failed = 0, 0
        for p, (rel, kind) in self.textures.items():
            if rel is None:
                continue
            dst = os.path.join(out, rel)
            if os.path.exists(dst):
                continue
            try:
                im = textures.decode(self.banks.read(p))
                if kind == "n":
                    im = textures.normal_map(im)
                elif kind == "ms":
                    im = textures.masks_to_metallic_smoothness(im)
                else:
                    im = im.convert("RGBA") if "A" in im.getbands() else im.convert("RGB")
                textures.save_png(im, dst, max_size)
                done += 1
            except textures.MissingASTC as e:
                if failed == 0:
                    self.report.warn(str(e))
                failed += 1
            except Exception as e:
                self.report.warn(f"{p}: {e}")
                failed += 1
        return done, failed


# --- parts ----------------------------------------------------------------------------------------------------------

def ident(*names):
    return "-".join(re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_") for n in names if n)


def pretty(name):
    n = name.strip("_").replace("_", " ")
    return re.sub(r"\s+", " ", n).strip().title()


def short(option):
    """`_WINGS_F` -> 'wings_f', `_SCLASSSHIP_A` -> 'sclassship_a'."""
    return option.id.strip("_").lower()


class Part:
    def __init__(self, id, slot, name, option, picks, within=None):
        self.id, self.slot, self.name, self.option, self.picks, self.within = id, slot, name, option, picks, within
        self.model = f"parts/{id}.glb"
        self.mounts = []
        self.triangles = 0
        self.bounds = None


def locator_mounts(asm, scale):
    """Weapon and exhaust mounts of an assembled subtree, in game units."""
    mounts = []
    k = scale * UNITS_PER_METRE
    seen = set()
    light = None
    for l in asm.lights:
        a = l.node.attrs
        if "engine" in l.node.name.lower() and "COL_R" in a:
            light = [round(float(a.get("COL_R", 1)), 3), round(float(a.get("COL_G", 1)), 3), round(float(a.get("COL_B", 1)), 3)]
            break

    def add(p, slot_type):
        pos = tuple(round(float(x) * k, 1) for x in p.position)
        if pos in seen:
            return
        seen.add(pos)
        m = {"slotType": slot_type, "position_engine": list(pos)}
        if slot_type == 3 and light:
            m["glowColor"] = light
        mounts.append(m)

    for p in asm.references:
        n = p.node.name.lower()
        if re.match(r"gun\d*ref", n) or n.startswith("shipgun") or n.startswith("gunref") or n.startswith("weaponref"):
            add(p, 0)
    for p in asm.locators:
        n = p.node.name.lower()
        if n == "trail" or n.startswith("engine_trail") or re.match(r"(jet|thruster)\d*$", n):
            add(p, 3)
    if not any(m["slotType"] == 3 for m in mounts):
        for p in asm.references:
            n = p.node.name.lower()
            if "engine" in n and "ref" in n:
                add(p, 3)
    return mounts


class KitBuilder:
    def __init__(self, banks, out, report, max_variants=MAX_VARIANTS, max_parts=MAX_PARTS_PER_SLOT):
        self.banks = banks
        self.out = out
        self.report = report
        self.materials = Materials(banks, report)
        self.max_variants = max_variants
        self.max_parts = max_parts
        self.descriptor_cache = {}

    def pick(self, scene_path, descriptor_bytes):
        """The chooser for a part scene's own descriptor: its likeliest option at every level."""
        d = self.descriptor_cache.get(scene_path)
        if d is None:
            d = self.descriptor_cache[scene_path] = descriptors.Descriptor(descriptor_bytes)
        picks = set()
        for g in d.groups:
            descriptors.default_picks(g, picks)
        return descriptors.chooser(d, picks)

    # -- what a class becomes --

    def plan(self, class_id, spec):
        """[(kit id, kit name, slots, [Part], scene path, descriptor)] for a class, or None when its files are missing."""
        proc = SPACECRAFT + spec["proc"]
        scene_path, desc_path = proc + ".scene.mbin", proc + ".descriptor.mbin"
        if not (self.banks.exists(scene_path) and self.banks.exists(desc_path)):
            self.report.warn(f"{class_id}: {scene_path} is not in the archives; skipped")
            return None
        d = descriptors.Descriptor(self.banks.read(desc_path))
        kits = []
        self.expand(class_id, spec["name"], [], d.groups, kits, scene_path, d)
        return kits

    def expand(self, kit_id, name, chain, groups, kits, scene_path, d):
        """One kit from `groups` as its slots, or, when they are one group of whole hulls with their own nested groups
        (the explorer's, shuttle's and exotic's trees), one kit per hull with that hull's groups as slots, recursively."""
        real = [g for g in groups if any(not o.is_none for o in g.options)]
        hulls = [o for o in real[0].options if not o.is_none] if len(real) == 1 else []
        if hulls and any(o.groups for o in hulls) and len(chain) < 4:
            g = real[0]
            for o in hulls:
                suffix = short(o).replace(g.slot, "", 1).strip("_") or short(o)
                kid = ident(kit_id, suffix) if len(hulls) > 1 else kit_id
                nm = f"{name} {pretty(suffix)}" if len(hulls) > 1 else name
                if o.groups:
                    self.expand(kid, nm, chain + [o], o.groups, kits, scene_path, d)
                else:
                    kits.append(self.kit(kid, nm, chain + [o], [], scene_path, d))
        else:
            kits.append(self.kit(kit_id, name, chain, real, scene_path, d))

    def kit(self, kit_id, name, chain, groups, scene_path, d):
        parts, slots = [], []
        if chain:
            picks = {o.id.lower() for o in chain}
            slots.append(chain[0].slot)
            parts.append(Part(ident(kit_id, "hull"), chain[0].slot, " ".join(pretty(o.name) for o in chain), chain[0], picks))
        within = chain[-1].name if chain else None
        for g in groups:
            slot, n = g.slot, 1   # a nested group named like the hull's (the explorer's cockpit in its cockpit frame),
            while slot in slots:   # or twice under one option (the shuttle's hull segments): a slot of its own each
                n += 1
                slot = f"{g.slot}{n}"
            slots.append(slot)
            parts.extend(self.option_parts(kit_id, g, within=within, slot=slot))
        return kit_id, name, slots, parts, scene_path, d

    def option_parts(self, kit_id, group, within=None, slot=None):
        slot = slot or group.slot
        out = []
        for o in group.options:
            if o.is_none and len(group.options) > 1:
                continue
            for v_id, v_name, picks in self.variants(o):
                if len(out) >= self.max_parts:
                    break
                out.append(Part(ident(kit_id, v_id if slot == group.slot else f"{slot}-{v_id}"), slot, v_name, o, picks, within))
        return out

    def variants(self, option):
        """[(id, name, picks)]: the option with its nested groups' likeliest choices, then one variant per other option
        of its first-level groups, up to max_variants."""
        base = {option.id.lower()}
        for g in option.groups:
            descriptors.default_picks(g, base)
        out = [(short(option), pretty(option.name), base)]
        for g in option.groups:
            first = descriptors.likeliest(g)
            for alt in g.options:
                if alt is first or len(out) >= self.max_variants:
                    continue
                picks = {option.id.lower()}
                for g2 in option.groups:
                    if g2 is g:
                        picks.add(alt.id.lower())
                        for g3 in alt.groups:
                            descriptors.default_picks(g3, picks)
                    else:
                        descriptors.default_picks(g2, picks)
                suffix = "none" if alt.is_none else short(alt)
                label = f"{pretty(option.name)} ({'plain' if alt.is_none else pretty(alt.name)})"
                out.append((f"{short(option)}-{suffix}", label, picks))
        return out

    # -- building --

    def build_class(self, class_id, spec, limit_parts=None):
        plan = self.plan(class_id, spec)
        if not plan:
            return []
        results = []
        for kit_id, name, slots, parts, scene_path, d in plan:
            if limit_parts:
                kept, per_slot = [], {}
                for p in parts:
                    if per_slot.get(p.slot, 0) < limit_parts:
                        kept.append(p)
                        per_slot[p.slot] = per_slot.get(p.slot, 0) + 1
                parts = kept
            log(f"  {kit_id}: slots {slots}, {len(parts)} parts to build")
            built = []
            for p in parts:
                try:
                    if self.build_part(scene_path, d, p, spec["scale"]):
                        built.append(p)
                    else:
                        self.report.note(f"{p.id}: no meshes (left out)")
                except Exception as e:
                    self.report.warn(f"{p.id}: {e}")
            kit = {"id": kit_id, "name": f"No Man's Sky {name} hulls", "slots": [s for s in slots if any(p.slot == s for p in built)],
                   "scale": spec["scale"], "yaw": 0, "parts": []}
            for p in built:
                entry = {"id": p.id, "slot": p.slot, "name": p.name, "model": p.model}
                if p.mounts:
                    entry["mounts"] = p.mounts
                kit["parts"].append(entry)
            if built:
                results.append((kit, name, built))
            else:
                self.report.warn(f"{kit_id}: no parts built; skipped")
        return results

    def build_part(self, scene_path, d, part, scale):
        asm = scene.Assembler(self.banks, descriptors.chooser(d, part.picks), pick=self.pick)
        asm.assemble_node(scene_path, part.option.name, within=part.within)
        w = glb.Writer()
        tris = 0
        lo, hi = np.array([1e9] * 3), np.array([-1e9] * 3)
        for i, placed in enumerate(scene.finest_meshes(asm.meshes)):
            if SKIP_NODES.search(placed.path):
                continue
            g = placed.scene.geometry
            name, cls = self.materials.name_for(placed)
            if cls in SKIP_MATERIAL_CLASSES:
                continue
            m = g.mesh(placed.node.name)
            if not len(m.indices):
                continue
            pos = geometry.apply(placed.matrix, m.positions)
            nrm = geometry.apply_normals(placed.matrix, m.normals)
            idx = m.indices[:, ::-1] if np.linalg.det(placed.matrix[:3, :3]) < 0 else m.indices
            lo, hi = np.minimum(lo, pos.min(0)), np.maximum(hi, pos.max(0))
            role = name.rsplit("_", 1)[1]
            mat = w.material(name, alpha_mode="BLEND" if role == "glass" else None, double_sided=cls == 15)
            w.add_mesh(f"{part.id}_{i:03d}_{placed.node.name}", pos, nrm, m.uvs, idx, mat)
            tris += m.triangle_count
        if tris == 0:
            return False
        part.triangles = tris
        part.bounds = (lo.tolist(), hi.tolist())
        part.mounts = locator_mounts(asm, scale)
        for ref in asm.missing:
            self.report.warn(f"{part.id}: referenced scene missing: {ref}")
        os.makedirs(os.path.join(self.out, "parts"), exist_ok=True)
        w.save(os.path.join(self.out, part.model))
        return True


# --- the mod ----------------------------------------------------------------------------------------------------------

def colour_slots():
    pal = {"paint": [], "lights": []}
    for c in PALETTE:
        e = {"id": c[0], "name": c[1], "color": c[2]}
        if len(c) > 3:
            e["metallic"], e["smoothness"] = c[3], c[4]
        pal["paint"].append(e)
    for c in LIGHTS:
        pal["lights"].append({"id": c[0], "name": c[1], "color": c[2]})
    slots = [{"id": "paint1", "name": "Primary colour", "palette": "paint", "default": "white", "targets": [{"material": "_paint1"}]},
             {"id": "paint2", "name": "Secondary colour", "palette": "paint", "default": "grey", "targets": [{"material": "_paint2"}]},
             {"id": "paint3", "name": "Tertiary colour", "palette": "paint", "default": "orange", "targets": [{"material": "_paint3"}]},
             {"id": "lights", "name": "Lights", "palette": "lights", "default": "cyan",
              "targets": [{"material": "_lights", "property": "emission", "intensity": 3}]},
             {"id": "engines", "name": "Engines", "palette": "lights", "default": "violet", "targets": [{"property": "engine"}]}]
    presets = [{"id": "stock", "name": "Stock", "colors": dict(DEFAULT_COLORS)},
               {"id": "night", "name": "Night", "colors": {"paint1": "black", "paint2": "grey", "paint3": "red", "lights": "red", "engines": "red"}},
               {"id": "frost", "name": "Frost", "colors": {"paint1": "silver", "paint2": "blue", "paint3": "white", "lights": "blue", "engines": "cyan"}},
               {"id": "sunset", "name": "Sunset", "colors": {"paint1": "orange", "paint2": "brown", "paint3": "yellow", "lights": "amber", "engines": "amber"}},
               {"id": "forest", "name": "Forest", "colors": {"paint1": "green", "paint2": "black", "paint3": "gold", "lights": "green", "engines": "green"}}]
    return pal, slots, presets


def ship_entry(kit, name, spec, parts):
    build = {}
    for slot in kit["slots"]:
        first = next((p for p in parts if p.slot == slot), None)
        if first:
            build[slot] = first.id
    chosen = [p for p in parts if p.id in build.values()]
    primaries = sum(1 for p in chosen for m in p.mounts if m["slotType"] == 0)
    exhausts = sum(1 for p in chosen for m in p.mounts if m["slotType"] == 3)
    build["colors"] = dict(DEFAULT_COLORS)
    entry = {"id": kit["id"], "name": name, "description": spec["description"], "race": 0,
             "armor": spec["armor"], "cargo": spec["cargo"], "handling": spec["handling"], "price": spec["price"],
             "slots": {"primary": max(2, min(primaries, 6)), "secondary": 2, "turret": 0, "equipment": spec["equipment"]},
             "kit": kit["id"], "kitType": kit["id"], "build": build,
             "engineGlowColor": [0.62, 0.16, 1.0],
             "dealer": {"chance": 3, "systemRace": -1, "minTechLevel": 3},
             "lounge": {"systemRace": -1, "minCampaign": 8, "minRank": 4, "chance": 10}}
    if exhausts == 0:
        lo = min((p.bounds[0][2] for p in chosen if p.bounds), default=-3.0)
        entry["mounts"] = [{"slotType": 3, "position_engine": [0, 0, round(lo * spec["scale"] * UNITS_PER_METRE, 1)]}]
    return entry


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")


def build(banks, out, classes=None, report=None, limit_parts=None, max_texture=MAX_TEXTURE):
    report = report or Report()
    t0 = time.time()
    classes = classes or list(CLASSES)
    os.makedirs(out, exist_ok=True)
    kb = KitBuilder(banks, out, report, MAX_VARIANTS, MAX_PARTS_PER_SLOT)
    kits, ships = [], []
    for class_id in classes:
        spec = CLASSES[class_id]
        log(f"{spec['name']} ({SPACECRAFT}{spec['proc']})")
        for kit, name, parts in kb.build_class(class_id, spec, limit_parts):
            pal, slots, presets = colour_slots()
            kit["palettes"], kit["colorSlots"], kit["presets"] = pal, slots, presets
            kits.append(kit)
            ships.append(ship_entry(kit, name, spec, parts))
            tris = sum(p.triangles for p in parts)
            log(f"  {kit['id']}: {len(parts)} parts, {tris} triangles ({time.time() - t0:.0f} s)")
    log("Textures...")
    done, failed = kb.materials.convert(out, max_texture)
    log(f"  {done} written" + (f", {failed} failed" if failed else ""))
    for kit in kits:
        kit["materials"] = kb.materials.kit_entries()
    write_json(os.path.join(out, "shipkits.json"), kits)
    write_json(os.path.join(out, "ships.json"), ships)
    write_json(os.path.join(out, "mod.json"), {
        "id": MOD_ID, "name": "No Man's Sky ships", "version": VERSION, "author": "built by nms_ships_importer",
        "description": "No Man's Sky's starships as customizable hulls: " + ", ".join(sorted({s["name"] for s in ships}))
                       + ". Built on this device from your own copy of No Man's Sky. Customize them in the hangar.",
        "credits": "Models and textures: No Man's Sky (c) Hello Games, from the player's own copy of the game. For personal use: don't share the built mod.",
        "multiplayerIgnore": ["parts/", "maps/"]})
    if report.missing_textures:
        report.warn(f"{len(report.missing_textures)} textures named by materials are not in the archives (e.g. {report.missing_textures[0]})")
    log(f"Done in {time.time() - t0:.0f} s: {len(kits)} kits, {sum(len(k['parts']) for k in kits)} parts -> {out}")
    return kits, ships, report


def zip_mod(out, zip_path):
    base = os.path.splitext(zip_path)[0]
    shutil.make_archive(base, "zip", os.path.dirname(out), os.path.basename(out))
    return base + ".zip"
