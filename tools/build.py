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
import math
import os
import re
import shutil
import struct
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from nms import animation, descriptors, geometry, hgpak, mbin, scene, textures   # noqa: E402
import glb   # noqa: E402

MOD_ID = "nms_ships"
VERSION = "0.1"
UNITS_PER_METRE = 20.0          # the remake's game units
MAX_VARIANTS = 4                # variants of one option over its nested groups
MAX_PARTS_PER_SLOT = 14
MAX_TEXTURE = 2048
TRANSITIONS = "pose"            # "pose": the ship in its flying pose (the end of its take-off), "loop": take-off and landing looped, "rest": as modelled
ANIMATIONS = True
PART_STATS = True              # small hull / cargo / handling / speed bonuses from each part's size
SOUNDS = True                  # the game's engine, boost and weapon sounds (needs a WEM decoder on the PATH)

SPACECRAFT = "models/common/spacecraft/"


def scene_file(name):
    """The archive path of a scene named relative to the spacecraft folder, or from the archive root ("models/...")."""
    return (name if name.startswith("models/") else SPACECRAFT + name) + ".scene.mbin"


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
    "living": dict(proc="s-class/bioparts/bioship_proc", name="Living Ship", scale=3.5, armor=280, cargo=45, handling=150, price=3800000,
                   equipment=11, description="A No Man's Sky living ship: a grown hull with organic engines. Customize it in the hangar."),
    # the fixed designs: one hull each (a kit of one part, so they take the paint slots like the others)
    "golden_vector": dict(scene="fighters/fighterclassicgold", name="Golden Vector", scale=4.0, armor=280, cargo=32, handling=165, price=2600000,
                          equipment=10, description="No Man's Sky's Golden Vector: the classic fighter in gold."),
    "rasamama": dict(scene="fighters/rasamamagold", name="Rasamama Gold", scale=4.0, armor=270, cargo=34, handling=160, price=2400000,
                     equipment=10, description="No Man's Sky's gold Rasamama fighter."),
    "utopia_speeder": dict(scene="fighters/vrspeeder", name="Utopia Speeder", scale=4.0, armor=250, cargo=30, handling=175, price=3200000,
                           equipment=10, description="No Man's Sky's Utopia Speeder: a sleek fixed-design racer."),
    "starborn_runner": dict(scene="fighters/vintageinterceptor", name="Starborn Runner", scale=4.0, armor=360, cargo=36, handling=160,
                            price=4200000, equipment=11, description="No Man's Sky's Starborn Runner: a sentinel-styled interceptor of fixed design."),
    "racer": dict(scene="fighters/wracer", name="Racer", scale=3.5, armor=240, cargo=30, handling=180, price=3000000,
                  equipment=10, description="No Man's Sky's racer: a long, narrow fixed hull built for speed."),
    "racer_se": dict(scene="fighters/wracerse", name="Racer SE", scale=3.5, armor=250, cargo=30, handling=180, price=3400000,
                     equipment=10, description="No Man's Sky's racer, special edition."),
    "boundary_herald": dict(scene="fighters/spookship", name="Boundary Herald", scale=1.5, armor=520, cargo=60, handling=110, price=6500000,
                            equipment=12, description="No Man's Sky's Boundary Herald: a disc hull fanning glowing feather wings."),
    "bio_fighter": dict(scene="s-class/bioparts/biofighter", name="Bio Fighter", scale=2.5, armor=300, cargo=40, handling=160, price=4500000,
                        equipment=11, description="No Man's Sky's grown fighter: a living hull of fixed shape."),
    "horizon_vector": dict(scene="fighters/fighterspecialswitch", name="Horizon Vector NX", scale=4.0, armor=270, cargo=32, handling=165, price=2800000,
                           equipment=10, description="No Man's Sky's Horizon Vector NX: the special-edition fighter with the droid wing."),
    # the small hostile craft: in the traffic only, never sold
    "police_ship": dict(scene="police/policeship", name="Sentinel Police Ship", scale=2.5, armor=200, cargo=10, handling=170, price=0, race=9,
                        equipment=6, traffic_only=True, description="No Man's Sky's sentinel police ship."),
    "drone_ship": dict(scene="drone/droneship", name="Sentinel Drone Ship", scale=2.0, armor=320, cargo=10, handling=120, price=0, race=9,
                       equipment=6, traffic_only=True, description="No Man's Sky's sentinel drone carrier."),
    "swarm_fighter": dict(scene="swarm/swarm", name="Brood Fighter", scale=1.5, armor=220, cargo=10, handling=170, price=0, race=9,
                          equipment=6, traffic_only=True, description="A No Man's Sky brood fighter of the swarm."),
    "swarm_drone": dict(scene="swarm/swarmdrone", name="Brood Drone", scale=4.0, armor=80, cargo=5, handling=190, price=0, race=9,
                        equipment=4, traffic_only=True, description="A No Man's Sky brood drone."),
    # the sentinels' drones (the robots folder: a scene path from the archive root), as the Void's small craft; the
    # sentinel drones look along -Z (their eye and guns lie there, their engine behind): `backward` turns them
    "sentinel_drone": dict(backward=True, scene="models/common/robots/drone", name="Sentinel Drone", scale=6.0, armor=120, cargo=5, handling=190, price=0, race=9,
                           equipment=4, traffic_only=True, hostile=True, description="A No Man's Sky sentinel drone: the eye that watches, and shoots."),
    "armoured_drone": dict(backward=True, scene="models/common/robots/dronearmoured", name="Sentinel Armoured Drone", scale=6.0, armor=260, cargo=5, handling=150, price=0, race=9,
                           equipment=5, traffic_only=True, hostile=True, description="A No Man's Sky armoured sentinel drone, plated and winged."),
    "summoner_drone": dict(backward=True, scene="models/common/robots/dronesummoner", name="Sentinel Summoner", scale=6.0, armor=160, cargo=5, handling=170, price=0, race=9,
                           equipment=4, traffic_only=True, hostile=True, description="A No Man's Sky summoner drone: it calls the swarm."),
    "corrupted_drone": dict(backward=True, scene="models/common/robots/corrupteddrone", name="Corrupted Sentinel", scale=5.0, armor=200, cargo=5, handling=160, price=0, race=9,
                            equipment=5, traffic_only=True, hostile=True, description="A No Man's Sky corrupted sentinel drone, grown over with crystal."),
    "medic_drone": dict(backward=True, scene="models/common/robots/dronemedic", name="Sentinel Repair Drone", scale=6.0, armor=140, cargo=5, handling=170, price=0, race=9,
                        equipment=4, traffic_only=True, hostile=True, description="A No Man's Sky repair drone of the sentinels, armed all the same."),
    "cargo_scan_drone": dict(scene="models/common/robots/cargoscandrone", name="Cargo Scan Drone", scale=2.5, armor=180, cargo=5, handling=140, price=0, race=9,
                             equipment=4, traffic_only=True, hostile=True, description="A No Man's Sky cargo scan drone: the sentinels' customs patrol."),
    "freighter_drone": dict(scene="models/common/robots/freighterdrone", name="Derelict Drone", scale=3.0, armor=150, cargo=5, handling=150, price=0, race=9,
                            equipment=4, traffic_only=True, hostile=True, description="A No Man's Sky security drone from a derelict freighter, still on patrol."),
}
# The capital ships: traffic freighters and battleships (the remake's capital ships), one model each from the game's
# freighter scenes (their descriptors' likeliest choices). The five standard frigates are not here: the game assembles
# their hulls in code from part tables, their scene files hold only the boardable details. `kind` is the remake's capital kind, `lod_budget`
# the triangles the model may hold (coarser LODs are taken per mesh family above it), `max_length` metres (the remake's
# flight level ends at 15 km), `hangar` the mod's ships a hostile one launches.
CAPITALS = {
    "freighter": dict(scene="industrial/freighter_proc", name="Freighter", kind="freighter", races=[0, 1, 2, 3], hull=3,
                      lod_budget=300000, max_length=2000, description="A No Man's Sky freighter, cruising the orbit."),
    "small_freighter": dict(scene="industrial/freightersmall_proc", name="Small Freighter", kind="freighter", races=[0, 1, 2, 3], hull=1,
                            lod_budget=200000, max_length=1000, description="A small No Man's Sky freighter."),
    "tiny_freighter": dict(scene="industrial/freightertiny_proc", name="Light Freighter", kind="freighter", races=[0, 1, 2, 3], hull=1,
                           lod_budget=200000, max_length=1000, description="A light No Man's Sky freighter."),
    "capital_freighter": dict(scene="industrial/capitalfreighter_proc", name="Capital Freighter", kind="battleship", races=[0, 1, 2, 3], hull=5,
                              lod_budget=400000, max_length=3500, description="A No Man's Sky capital freighter: a flying dock the size of a city."),
    "pirate_dreadnought": dict(scene="industrial/piratefreighter", name="Pirate Dreadnought", kind="battleship", races=[8], hull=8,
                               lod_budget=500000, max_length=4500, hangar=["fighter"], description="A No Man's Sky pirate dreadnought: cannons along every trench, raiders in its bays."),
    "sentinel_capital": dict(scene="police/policefreighter", name="Sentinel Capital Ship", kind="battleship", races=[9], hull=5,
                             lod_budget=400000, max_length=2500, hangar=["sentinel"], description="A No Man's Sky sentinel capital ship, bristling with turrets."),
    "living_frigate": dict(scene="frigates/livingfrigate_proc_lod0", name="Living Frigate", kind="freighter", races=[0, 1, 2, 3], hull=2,
                           lod_budget=250000, max_length=800, description="A No Man's Sky living frigate: a grown hull in the traffic."),
    # the frigates and the Normandy: the hull is the LOD0 scene, the base scene holds the engine trails and the LOD switch
    "combat_frigate": dict(scene="frigates/combatfrigatelod0", also=["frigates/combatfrigate"], name="Combat Frigate", kind="freighter", races=[0, 1, 2, 3],
                           hull=2, lod_budget=900000, max_length=600, description="A No Man's Sky combat frigate."),
    "science_frigate": dict(scene="frigates/sciencefrigatelod0", also=["frigates/sciencefrigate"], name="Science Frigate", kind="freighter", races=[0, 1, 2, 3],
                            hull=2, lod_budget=900000, max_length=600, description="A No Man's Sky exploration frigate."),
    "diplomatic_frigate": dict(scene="frigates/diplomaticfrigatelod0", also=["frigates/diplomaticfrigate"], name="Diplomatic Frigate", kind="freighter", races=[0, 1, 2, 3],
                               hull=2, lod_budget=900000, max_length=600, description="A No Man's Sky trade frigate."),
    "industrial_frigate": dict(scene="frigates/industrialfrigatelod0", also=["frigates/industrialfrigate"], name="Industrial Frigate", kind="freighter", races=[0, 1, 2, 3],
                               hull=2, lod_budget=1200000, max_length=600, description="A No Man's Sky industrial frigate."),
    "support_frigate": dict(scene="frigates/supportfrigatelod0", also=["frigates/supportfrigate"], name="Support Frigate", kind="freighter", races=[0, 1, 2, 3],
                            hull=2, lod_budget=900000, max_length=600, description="A No Man's Sky support frigate."),
    "normandy": dict(scene="frigates/normandyfrigatelod0", also=["frigates/normandyfrigate"], name="Normandy SR1", kind="freighter", races=[0],
                     hull=2, lod_budget=250000, max_length=600, description="The Normandy SR1, No Man's Sky's frigate from Mass Effect."),
    "ghost_frigate": dict(scene="frigates/ghostshipfrigatelod0", also=["frigates/ghostshipfrigate"], name="Ghost Frigate", kind="freighter", races=[9],
                          hull=2, lod_budget=300000, max_length=600, description="No Man's Sky's ghost ship: a derelict frigate drifting the lanes."),
    "pirate_cruiser": dict(scene="industrial/piratecruiserlod0", also=["industrial/piratecruiser"], name="Pirate Cruiser", kind="battleship", races=[8],
                           hull=3, lod_budget=500000, max_length=600, hangar=["fighter"], description="A No Man's Sky pirate cruiser."),
    "old_freighter": dict(scene="industrial/freighter_a", name="Old Freighter", kind="freighter", races=[0, 1, 2, 3],
                          hull=2, lod_budget=250000, max_length=800, description="No Man's Sky's early freighter hull."),
    "freight_ship": dict(scene="industrial/freightship01", name="Freight Ship", kind="freighter", races=[0, 1, 2, 3],
                         hull=2, lod_budget=250000, max_length=600, description="A No Man's Sky freight ship."),
    "small_transport": dict(scene="industrial/smalltransport2", name="Small Transport", kind="freighter", races=[0, 1, 2, 3],
                            hull=1, lod_budget=100000, max_length=400, description="A small No Man's Sky transport."),
    "swarm_frigate": dict(scene="swarm/swarmfrigate", name="Brood Frigate", kind="battleship", races=[9], hull=4,
                          lod_budget=500000, max_length=2500, hangar=["swarm_fighter"], description="A No Man's Sky brood frigate of the swarm, hostile."),
    "swarm_hive": dict(scene="swarm/swarmhive", name="Brood Hive", kind="battleship", races=[9], hull=8,
                       lod_budget=600000, max_length=3000, hangar=["swarm_fighter"], description="A No Man's Sky brood hive: the swarm's mothership."),
}
TURRET_ITEMS = [48, 49, 47]          # the game's blaster-bolt turrets, cycled over a capital ship's turret mounts
MAX_TURRETS = 8                      # the remake's limit for a capital ship's hardpoints in multiplayer copies
TURRET_NODES = re.compile(r"(turretorigin|^turret|refturret|antishipturret|smallturretref|refheavycannon|turretpolice|cannon)", re.I)
HANGAR_NODES = re.compile(r"hangarroot", re.I)

# Who flies each class as NPC traffic (the remake's "Mod ships in traffic" share): the trader races, the pirates (8) with the
# game's own habit of flying its fighters, haulers and shuttles, the sentinels (9, the Void) with their interceptors.
TRAFFIC = {"fighter": ([0, 1, 2, 3, 8], 3), "hauler": ([0, 1, 2, 3, 8], 2), "explorer": ([0, 1, 2, 3], 2), "shuttle": ([0, 1, 2, 3, 8], 2),
           "exotic": ([0, 1, 2, 3], 1), "solar": ([0, 1, 2, 3], 1), "living": ([0, 1, 2, 3], 1), "sentinel": ([9], 3)}
FIXED_TRAFFIC = ([0, 1, 2, 3], 1)

SKIP_MATERIAL_CLASSES = {2, 12, 22, 24}   # Additive (engine jets: the remake draws its own flames), Decal, GunAdditive, GunGlow
EMISSIVE_CLASSES = {18, 19}               # Glow, GlowTranslucent
TRANSLUCENT_CLASSES = {62, 63, 15}        # Translucent, TranslucentPostScene, DoubleSided
SKIP_NODES = re.compile(r"(landinggear|landing_gear|frontpad|leftpad|rightpad|backpad|_gear\b|shadowmesh|shielddata|fxsphere|vfxref|engineglowpoly|gravitycube|gravityvolume|gravcapsule|hoverpad|biggsplatform|landingzone|critmesh|patroleye|investeye|engineeffectpatrol|engineeffectinvest)", re.I)   # and the drones' critical-hit mesh and their patrol / investigate eyes (the attack ones stay)   # and the corvette docking pads the frigates carry   # gear and pads; the capital ships' shield spheres, engine effect planes and gravity volumes
WEAPON_SCENES = re.compile(r"/shared/weapons/", re.I)   # the ship gun (one model for every class), a fixed part of the hull


def under_weapon(placed):
    """Whether a placed node sits inside the gun's referenced scene (its meshes are kept, its idle and shooting loops
    are not: the remake draws the shots; its take-off pose is)."""
    return any(n.type == "REFERENCE" and WEAPON_SCENES.search(n.scenegraph) for n in placed.chain)

PALETTE = [("white", "Snow White", "#F2F2F2"), ("silver", "Silver", "#B8BCC2", 0.9, 0.7), ("grey", "Graphite", "#5A5E63"),
           ("black", "Jet", "#1E1E22"), ("red", "Vermilion", "#C8321E"), ("orange", "Amber", "#E07B1A"),
           ("yellow", "Sulphur", "#E2C33A"), ("green", "Verdant", "#3E9B4B"), ("teal", "Teal", "#2E9C9A"),
           ("blue", "Cobalt", "#2A5DC8"), ("purple", "Violet", "#7A3FB8"), ("pink", "Magenta", "#C83C9B"),
           ("brown", "Rust", "#7A4A2A"), ("gold", "Gold", "#C9A227", 1.0, 0.75)]
LIGHTS = [("white", "White", "#FFFFFF"), ("cyan", "Cyan", "#49D6FF"), ("amber", "Amber", "#FFB347"), ("red", "Red", "#FF4A3A"),
          ("green", "Green", "#4AFF7A"), ("violet", "Violet", "#B06CFF"), ("blue", "Blue", "#4A6AFF")]
HULL_NAMES = {"aroot": "A", "droot": "D", "roy": "Royal", "squ": "Squid", "double": "Twin", "single": "Single",
              "boxdouble": "Box", "cylinderdouble": "Cylinder", "cylinderstart": "Cylinder", "box": "Box"}   # the descriptors' hull ids as names
DEFAULT_COLORS = {"paint1": "white", "paint2": "grey", "paint3": "orange", "lights": "cyan", "engines": "violet"}


def log(msg):
    print(msg, flush=True)


class Report:
    extras = {}
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

JET_MAP = re.compile(r"engine_jet", re.I)
GLOW_MAP = re.compile(r"engineglow", re.I)
STAGE_BOOST = re.compile(r"boost", re.I)   # the staged jet engine's boost stage (the decomp: STAGE1 lit by thrust, STAGE2 by speed and the pulse drive, BOOST by boost)
FLAME_NOISE = "maps/engine_jet_noise.png"


def engine_role(mat):
    """'flame' for the jet cones the game draws additively over thrust, 'engineglow' for the glow discs, else None."""
    if not mat:
        return None
    maps = " ".join(s["map"] for s in mat["samplers"])
    if mat["material_class"] == 2 and (JET_MAP.search(maps) or mat["name"].lower().startswith("enginejet") or "engine" in maps.lower()):
        return "flame"
    if mat["material_class"] in EMISSIVE_CLASSES and GLOW_MAP.search(maps):
        return "engineglow"
    return None


def role_of(material_name, mat):
    n = material_name.lower()
    special = engine_role(mat)
    if special:
        return special
    if "primary" in n:
        return "paint1"
    if "secondary" in n:
        return "paint2"
    if "tertiary" in n:
        return "paint3"
    if mat and any(s["name"].lower() in ("gmasksmap", "gnormalmap") for s in mat["samplers"]):
        pass   # a full surface (masks / normal maps): the living ships' skins are "Glow" class but not light cards
    elif mat and mat["material_class"] in EMISSIVE_CLASSES or "light" in n or "glow" in n:
        return "lights"
    if "trans" in n or "glass" in n:
        return "glass"
    return "plain"


def uniform(mat, name, default=(1, 1, 1, 1)):
    for u in mat["uniforms"]:
        if u["name"] == name:
            return u["values"]
    return list(default)


# textures the game's materials name but the game doesn't ship, and the shipped one that stands in for each (the
# shuttles' materials name an overlay normal map; the hull's own base normal map is of the same surface)
STAND_IN_TEXTURES = {"shuttle.overlay.normal.dds": "shuttle.base.normal.dds"}


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
            for missing, stand_in in STAND_IN_TEXTURES.items():
                if p.endswith(missing) and self.banks.exists(p[: -len(missing)] + stand_in):
                    self.report.note(f"{p} is not in the archives: {stand_in} stands in")
                    rel = self.texture(p[: -len(missing)] + stand_in, kind)
                    self.textures[p] = (rel, kind)
                    return rel
            self.report.missing_textures.append(p)
            self.textures[p] = (None, kind)
            return None
        stem = re.sub(r"[^a-z0-9]+", "_", p.replace("textures/common/spacecraft/", "").replace("textures/", "").rsplit(".", 1)[0]).strip("_")
        rel = f"maps/{stem}_{kind}.png"
        self.textures[p] = (rel, kind)
        return rel

    def name_for(self, placed, engine_colour=None):
        """(GLB material name, NMS material class) of a placed mesh's material. `engine_colour` is the engine light's
        colour of the assembly, the colour of its flames and glows."""
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
            if role in ("flame", "engineglow"):
                colour = tuple(engine_colour or (0.62, 0.16, 1.0))
            key = (tuple(sorted((k, scene.game_path(v)) for k, v in maps.items())), cls, colour, role)
        if key in self.names:
            return self.names[key], cls
        index = len(self.names)
        name = f"mat_{index:04d}_{role}"
        self.names[key] = name
        entry = {"material": name, "_nms": nms_name}
        if role == "flame":
            # the jet cones: the remake's engine flames (lit by thrust, the boost cards while boosting), in the engine's colour
            self.flame_noise()
            entry.update({"flame": True, "flameLength": 0.5, "emissionColor": [round(float(x), 3) for x in colour[:3]], "emissionIntensity": 2.5,
                          "boostColor": [round(0.5 + 0.5 * float(x), 3) for x in colour[:3]], "flameNoise": FLAME_NOISE})
            self.entries[key] = entry
            return name, cls
        if role == "engineglow":
            # the glow discs at the nozzles: lit with the engines, steady while they run
            entry.update({"engine": True, "engineIdle": 1, "emissionColor": [round(float(x), 3) for x in colour[:3]], "emissionIntensity": 2})
            if "diffuse" in maps:
                rel = self.texture(maps["diffuse"], "g")
                if rel:
                    entry["emission"] = rel
            entry["color"] = [0, 0, 0]
            self.entries[key] = entry
            return name, cls
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
            if any(k in e for k in ("diffuse", "normal", "metallicSmoothness", "emissionColor", "color", "opacity", "flame", "engine")):
                out.append({k: v for k, v in e.items() if not k.startswith("_")})
        return out

    def ship_entries(self, names):
        """The entries for a plain ship's `materials` (matched by the renderers' names, which carry `__<material>`)."""
        out = []
        for e in self.kit_entries():
            if e["material"] in names:
                out.append({"mesh": "__" + e["material"], **{k: v for k, v in e.items() if k != "material"}})
        return out

    def flame_noise(self):
        """The flame flicker noise from the game's jet texture: its streaks across the jet, tiled."""
        if FLAME_NOISE in self.textures.values() or "_noise" in self.textures:
            return
        self.textures["_noise"] = (FLAME_NOISE, "noise")

    def convert(self, out, max_size=MAX_TEXTURE):
        done, failed = 0, 0
        for p, (rel, kind) in self.textures.items():
            if rel is None:
                continue
            dst = os.path.join(out, rel)
            if os.path.exists(dst):
                continue
            try:
                if kind == "noise":
                    textures.save_png(flame_noise_image(self.banks), dst)
                    done += 1
                    continue
                im = textures.decode(self.banks.read(p))
                if kind == "g":
                    im = im.convert("RGBA")
                    rgb = np.asarray(im).astype(np.float32)
                    lum = (rgb[..., :3].max(axis=2) * rgb[..., 3] / 255.0).astype(np.uint8)   # the disc's shape as grey
                    im = Image.merge("RGB", [Image.fromarray(lum)] * 3)
                elif kind == "n":
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


JET_TEXTURE = "textures/effects/ship/engine_jet.dds"


def flame_noise_image(banks, size=256):
    """A tiling grey noise from the jet texture's streaks (the rows across the jet, taken where the streaks show, mirrored
    to tile); a plain noise when the game lacks the texture."""
    rng = np.random.default_rng(7)
    if banks is not None and banks.exists(JET_TEXTURE):
        try:
            im = textures.decode(banks.read(JET_TEXTURE)).convert("RGBA")
            a = np.asarray(im).astype(np.float32)
            w = a.shape[1]
            band = a[:, w // 4: w // 2, 0]   # the red channel, across the jet, where the streaks are
            band = (band - band.min()) / max(band.max() - band.min(), 1e-6)
            tile = np.concatenate([band, band[:, ::-1]], axis=1)
            tile = np.concatenate([tile, tile[::-1, :]], axis=0)
            img = Image.fromarray((tile * 255).astype(np.uint8), "L").resize((size, size), Image.BILINEAR)
            return img.convert("RGB")
        except Exception:
            pass
    noise = (rng.random((size, size)) * 255).astype(np.uint8)
    return Image.fromarray(noise, "L").convert("RGB")


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
        self.animated = False
        self.stats = {}
        self.engine_colour = None
        self.lod_floor = 0
        self.material_names = []
        self.extra_scenes = []   # more scenes assembled into the same model (a frigate's base scene with its trails)
        self.keep = None         # a regex a mesh's path must match to be drawn (a station's exterior)
        self.skip = None         # a regex of more paths left out
        self.frame = None        # a 4x4 applied to everything (a station turned to face its docking tunnel along +Z)
        self.drop_detail = False   # at LOD floor 2 and up, leave out the mesh families that have no LODs (interior props)

    def allows(self, path):
        if self.keep is not None and not self.keep.search(path):
            return False
        return not (self.skip is not None and self.skip.search(path))


def engine_colour(asm):
    """The colour of the assembly's engine light (the decomp: lights whose name holds ENGINE light the thrusters), or None."""
    for l in asm.lights:
        a = l.node.attrs
        if "engine" in l.node.name.lower() and "COL_R" in a:
            return [round(float(a.get("COL_R", 1)), 3), round(float(a.get("COL_G", 1)), 3), round(float(a.get("COL_B", 1)), 3)]
    for l in asm.lights:
        a = l.node.attrs
        if "COL_R" in a and float(a.get("INTENSITY", 0)) > 1:
            return [round(float(a.get("COL_R", 1)), 3), round(float(a.get("COL_G", 1)), 3), round(float(a.get("COL_B", 1)), 3)]
    return None


def socket_scale(p, scale):
    """The size of an exhaust's effects from its trail locator's scale (the game sizes its trail by it), in the remake's
    socket units (EVERSPACE 2's default socket is 1)."""
    s = float(p.node.transform["scale"][0]) * scale / 2.0
    return round(max(0.3, min(2.5, s)), 2)


def locator_mounts(asm, scale, overrides=None):
    """Weapon, exhaust and booster mounts of an assembled subtree, in game units (in the flying pose when `overrides`
    has one): guns from the gun references, exhausts from the TRAIL locators (the game's engine trails), boosters from
    the CONTRAIL locators (its wingtip contrails, drawn while boosting)."""
    mounts = []
    k = scale * UNITS_PER_METRE
    seen = set()
    light = engine_colour(asm)

    def add(p, slot_type, extra=None):
        pos = tuple(round(float(x) * k, 1) for x in (p.world(overrides)[:3, 3] if overrides else p.position))
        if pos in seen:
            return
        seen.add(pos)
        m = {"slotType": slot_type, "position_engine": list(pos)}
        if slot_type == 3 and light:
            m["glowColor"] = light
        if extra:
            m.update(extra)
        mounts.append(m)

    for p in asm.references:
        n = p.node.name.lower()
        if re.match(r"gun\d*ref", n) or n.startswith("shipgun") or n.startswith("gunref") or n.startswith("weaponref"):
            add(p, 0)
    if not mounts:   # the sentinel interceptors' guns are part of the hull mesh: their muzzles are EXT_SHOOT locators
        for p in asm.locators:
            if re.match(r"(ext_)?shoot\d*$", p.node.name.lower()):
                add(p, 0)
    # No Man's Sky has no second weapon class: rockets leave the same gun points, so the secondaries sit there too
    mounts += [{"slotType": 1, "position_engine": list(m["position_engine"])} for m in mounts if m["slotType"] == 0]
    for p in asm.locators:
        n = p.node.name.lower()
        if n.startswith("trail") or n.startswith("engine_trail") or re.match(r"(jet|thruster)\d*$", n):
            add(p, 3, {"socketScale": socket_scale(p, scale)})
    if not any(m["slotType"] == 3 for m in mounts):
        for p in asm.references:
            n = p.node.name.lower()
            if "engine" in n and ("ref" in n or "reactor" in n):   # thruster references; the frigates' engine effect references
                add(p, 3, {"socketScale": 1.0})
    for p in asm.locators:
        if p.node.name.lower().startswith("contrail"):
            add(p, 5, {"socketScale": 0.5})   # wingtip contrails: thin
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
        self.anim_cache = {}
        self.base_cache = {}

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
        if "scene" in spec:   # a fixed design: the whole scene (its own descriptor's likeliest choices) as one hull part
            scene_path = scene_file(spec["scene"])
            if not self.banks.exists(scene_path):
                self.report.warn(f"{class_id}: {scene_path} is not in the archives; skipped")
                return None
            desc_path = scene_path[: -len(".scene.mbin")] + ".descriptor.mbin"
            d, picks = None, set()
            if self.banks.exists(desc_path):
                d = descriptors.Descriptor(self.banks.read(desc_path))
                for g in d.groups:
                    descriptors.default_picks(g, picks)
            part = Part(ident(class_id, "hull"), "hull", spec["name"], None, picks)
            return [(class_id, spec["name"], ["hull"], [part], scene_path, d)]
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
                nm = f"{name} {HULL_NAMES.get(suffix, pretty(suffix))}" if len(hulls) > 1 else name
                if o.groups:
                    self.expand(kid, nm, chain + [o], o.groups, kits, scene_path, d)
                else:
                    kits.append(self.kit(kid, nm, chain + [o], [], scene_path, d))
        else:
            kits.append(self.kit(kit_id, name, chain, real, scene_path, d))

    def kit(self, kit_id, name, chain, groups, scene_path, d):
        parts, slots = [], []
        if self.has_base(scene_path, d):   # the model's meshes and gun points outside every option (the sentinels' guns)
            slots.append("base")
            parts.append(Part(ident(kit_id, "base"), "base", "Hull", None, set()))
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

    def has_base(self, scene_path, d):
        """Whether the procedural scene draws meshes or holds gun points outside every option (one check per scene)."""
        if scene_path in self.base_cache:
            return self.base_cache[scene_path]
        result = False
        if self.banks is not None and self.banks.exists(scene_path):
            asm = scene.Assembler(self.banks, descriptors.chooser(d, set()), pick=self.pick)
            asm.assemble(scene_path)
            result = any(not SKIP_NODES.search(p.path) for p in asm.meshes) or \
                any(re.match(r"(ext_)?shoot\d*$", p.node.name.lower()) for p in asm.locators)
        self.base_cache[scene_path] = result
        return result

    def option_parts(self, kit_id, group, within=None, slot=None):
        slot = slot or group.slot
        out = []
        for o in group.options:
            if (o.is_none and len(group.options) > 1) or descriptors.lod_twin(o, group):
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
                if alt is first or len(out) >= self.max_variants or descriptors.lod_twin(alt, g):
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
            backward = "scene" in spec and (spec.get("backward", False) or faces_backward(built))
            kit = {"id": kit_id, "name": f"No Man's Sky {name} hulls", "slots": [s for s in slots if any(p.slot == s for p in built)],
                   "scale": spec["scale"], "yaw": 180 if backward else 0, "parts": []}
            if PART_STATS:
                part_stats(built)
            for p in built:
                if backward:
                    p.mounts = turn_mounts(p.mounts)
                entry = {"id": p.id, "slot": p.slot, "name": p.name, "model": p.model}
                if p.mounts:
                    entry["mounts"] = p.mounts
                if p.stats:
                    entry["stats"] = p.stats
                kit["parts"].append(entry)
            if built:
                results.append((kit, name, built))
            else:
                self.report.warn(f"{kit_id}: no parts built; skipped")
        return results

    # -- animation --

    def animations_for(self, asm):
        """What moves in an assembled part, from the entities its nodes attach: `overrides` {node: local matrix}
        (the flying pose), `loop` [(node, rotations, translations, scales)] per frame lists (None = not animated),
        `spins` [(node, axis, turns per second)], `transitions` {name: tracks} (take-off, landing, for later)."""
        out = {"overrides": {}, "loop": [], "spins": [], "transitions": {}}
        if not ANIMATIONS:
            return out
        for placed in asm.attachments:
            weapon = under_weapon(placed)
            ent = scene.game_path(placed.node.attrs["ATTACHMENT"])
            if not self.banks.exists(ent):
                continue
            try:
                comps = animation.entity_components(self.banks.read(ent))
            except mbin.MBINError:
                continue
            rot = comps.get(animation.HASH_ROTATION_COMPONENT)
            if rot and abs(rot["speed"]) > 1e-6 and not weapon:
                out["spins"].append((placed.node, rot["axis"], rot["speed"]))
            comp = comps.get(animation.HASH_ANIMATION_COMPONENT)
            if not comp:
                continue
            nodes = {n.name.lower(): n for n in placed.scene.root.walk()}
            loop = None if weapon else animation.flight_loop(comp)
            if loop:
                an = self.animation_file(loop["filename"])
                if an:
                    for name in an.nodes:
                        node = nodes.get(name.lower())
                        if node is None:
                            continue
                        r_on, s_on, t_on = an.animated(name)
                        if not (r_on or s_on or t_on):
                            continue
                        track = an.track_at(name, animation.FPS)
                        out["loop"].append((node, [t[0] for t in track] if r_on else None, [t[2] for t in track] if t_on else None,
                                            [t[1] for t in track] if s_on else None))
            for kind in ("TAKEOFF", "LANDING", "THRUST"):
                tr = animation.transition(comp, kind)
                if not tr:
                    continue
                an = self.animation_file(tr["filename"])
                if not an or not an.frames:
                    continue
                tracks = []
                for name in an.nodes:
                    node = nodes.get(name.lower())
                    if node is None:
                        continue
                    r_on, s_on, t_on = an.animated(name)
                    if not (r_on or s_on or t_on):
                        continue
                    track = an.track_at(name, animation.FPS)
                    tracks.append((node, [t[0] for t in track] if r_on else None, [t[2] for t in track] if t_on else None,
                                   [t[1] for t in track] if s_on else None))
                    if (kind == "TAKEOFF" and TRANSITIONS == "pose") or kind == "THRUST":   # THRUST: the jets grown to full thrust
                        rot, sc, trn = track[-1]
                        t0 = node.transform
                        q = rot if rot else glb.quaternion_from_matrix(geometry.transform_matrix(t0)[:3, :3] / np.maximum(np.linalg.norm(geometry.transform_matrix(t0)[:3, :3], axis=0), 1e-9))
                        out["overrides"][node] = animation.local_matrix(q, sc if sc else t0["scale"], trn if trn else t0["trans"])
                if tracks and kind != "THRUST":
                    out["transitions"][kind.lower()] = tracks
        return out

    def animation_file(self, filename):
        f = scene.game_path(filename)
        if f in self.anim_cache:
            return self.anim_cache[f]
        an = None
        if self.banks.exists(f):
            try:
                an = animation.Animation(self.banks.read(f))
            except (mbin.MBINError, struct.error) as e:
                self.report.note(f"{f}: {e}")
        self.anim_cache[f] = an
        return an

    # -- building --

    def build_part(self, scene_path, d, part, scale):
        asm = scene.Assembler(self.banks, descriptors.chooser(d, part.picks) if d else None, pick=self.pick)
        if part.option is None:   # the base: everything outside the options (or a fixed design's whole scene)
            asm.assemble(scene_path)
            for extra in part.extra_scenes:
                asm.assemble(extra)
        else:
            asm.assemble_node(scene_path, part.option.name, within=part.within)
        anims = self.animations_for(asm)
        overrides = anims["overrides"]
        animated = {node for node, *_ in anims["loop"]} | {node for node, *_ in anims["spins"]}
        if TRANSITIONS == "loop":
            for tracks in anims["transitions"].values():
                animated |= {node for node, *_ in tracks}
        w = glb.Writer()
        glb_nodes = {}    # scene node -> glb node index (the hierarchy of the animated parts)
        chains = {}       # scene node -> its chain (root .. node), from the placed meshes
        tris = 0
        lo, hi = np.array([1e9] * 3), np.array([-1e9] * 3)

        def ensure(chain):
            """GLB nodes for a chain of scene nodes (a scene root contributes no transform)."""
            parent = None
            for i, n in enumerate(chain):
                if n in glb_nodes:
                    parent = glb_nodes[n]
                    continue
                if n is n.scene.root:
                    M = np.identity(4)
                else:
                    M = overrides.get(n, n.local)
                t, r, sc = glb.trs(M)
                parent = glb_nodes[n] = w.add_node(n.name if n is not n.scene.root else n.name.rsplit("\\", 1)[-1], parent, t, r, sc)
            return parent

        drawn = [p for p in asm.meshes if not SKIP_NODES.search(p.path) and part.allows(p.path)]
        if part.frame is not None:   # a framed model is drawn flat: no node hierarchy, no animations
            animated = set()
        colour = engine_colour(asm)
        for i, placed in enumerate(scene.finest_meshes(drawn, part.lod_floor, part.drop_detail and part.lod_floor >= 2)):
            g = placed.scene.geometry
            name, cls = self.materials.name_for(placed, colour)
            role = name.rsplit("_", 1)[1]
            if cls in SKIP_MATERIAL_CLASSES and role != "flame":
                continue
            m = g.mesh(placed.node.name)
            if not len(m.indices):
                continue
            mat = w.material(name, alpha_mode="BLEND" if role in ("glass", "flame") else None, double_sided=cls == 15 or role == "flame")
            uvs, uvs2 = m.uvs, None
            if role == "flame":
                # a flame card: u from 0 at the nozzle to 1 at the tip (the jet points backward, -Z, in the ship's frame),
                # the second channel's y naming the card: 0.5 a main card lit by thrust (STAGE1, STAGE2), 0.25 a boost card
                world = placed.world(overrides) if overrides else placed.matrix
                z = geometry.apply(world, m.positions)[:, 2]
                span = max(float(z.max() - z.min()), 1e-6)
                uvs = np.stack([(z.max() - z) / span, m.uvs[:, 1]], axis=1).astype(np.float32)
                boost = any(STAGE_BOOST.search(n.name) for n in placed.chain)
                uvs2 = np.full((len(m.positions), 2), 0.25 if boost else 0.5, np.float32)
            moving = [n for n in placed.chain if n in animated]
            if moving:
                for k in range(len(placed.chain)):
                    chains.setdefault(placed.chain[k], placed.chain[: k + 1])
                parent = ensure(placed.chain[:-1])
                M = overrides.get(placed.node, placed.node.local)
                t, r, sc = glb.trs(M)
                idx = m.indices[:, ::-1] if np.linalg.det(placed.world(overrides)[:3, :3]) < 0 else m.indices
                glb_nodes[placed.node] = w.add_mesh(f"{part.id}_{i:03d}_{placed.node.name}__{name}", m.positions, m.normals, uvs, idx, mat,
                                                    uvs2=uvs2, parent=parent, translation=t, rotation=r, scale=sc)
                world = placed.world(overrides)
                pos = geometry.apply(world, m.positions)
            else:
                world = placed.world(overrides) if overrides else placed.matrix
                if part.frame is not None:
                    world = part.frame @ world
                pos = geometry.apply(world, m.positions)
                nrm = geometry.apply_normals(world, m.normals)
                idx = m.indices[:, ::-1] if np.linalg.det(world[:3, :3]) < 0 else m.indices
                w.add_mesh(f"{part.id}_{i:03d}_{placed.node.name}__{name}", pos, nrm, uvs, idx, mat, uvs2=uvs2)
            lo, hi = np.minimum(lo, pos.min(0)), np.maximum(hi, pos.max(0))
            tris += m.triangle_count
        part.mounts = locator_mounts(asm, scale, overrides) if part.frame is None else []
        part.scale = scale
        part.engine_colour = colour
        if tris == 0 and not (part.option is None and part.mounts):
            return False
        self.write_animations(w, anims, glb_nodes, chains, ensure, overrides)
        part.triangles = tris
        part.bounds = (lo.tolist(), hi.tolist()) if tris else None
        part.animated = bool(w.animations)
        for ref in asm.missing:
            self.report.warn(f"{part.id}: referenced scene missing: {ref}")
        part.material_names = sorted(w.material_index)
        os.makedirs(os.path.join(self.out, os.path.dirname(part.model)), exist_ok=True)
        w.save(os.path.join(self.out, part.model))
        return True

    # -- capital ships --

    def build_capital(self, cid, spec):
        """A capital ship: one model from its scene (the descriptor's likeliest choices), coarser LODs until it fits its
        triangle budget, shrunk to its longest length; its turrets, hangar and exhausts as mounts. Returns the ship entry."""
        scene_path = scene_file(spec["scene"])
        if not self.banks.exists(scene_path):
            self.report.warn(f"{cid}: {scene_path} is not in the archives; skipped")
            return None
        desc_path = scene_path[: -len(".scene.mbin")] + ".descriptor.mbin"
        d, picks = None, set()
        if self.banks.exists(desc_path):
            d = descriptors.Descriptor(self.banks.read(desc_path))
            for g in d.groups:
                descriptors.default_picks(g, picks)
        # the size first (a cheap pass over the finest meshes' bounds), then the shrink
        extra = [SPACECRAFT + x + ".scene.mbin" for x in spec.get("also", []) if self.banks.exists(SPACECRAFT + x + ".scene.mbin")]
        asm = scene.Assembler(self.banks, descriptors.chooser(d, picks) if d else None, pick=self.pick)
        asm.assemble(scene_path)
        for x in extra:
            asm.assemble(x)
        lo, hi = np.array([1e9] * 3), np.array([-1e9] * 3)
        for placed in scene.finest_meshes([p for p in asm.meshes if not SKIP_NODES.search(p.path)]):
            m = placed.scene.geometry.mesh(placed.node.name)
            if len(m.indices):
                pos = geometry.apply(placed.matrix, m.positions)
                lo, hi = np.minimum(lo, pos.min(0)), np.maximum(hi, pos.max(0))
        length = float(hi[2] - lo[2]) if hi[2] > lo[2] else 1.0
        shrink = min(1.0, spec["max_length"] / length)
        part = Part(cid, "hull", spec["name"], None, picks)
        part.model = f"models/{cid}.glb"
        part.extra_scenes = extra
        for floor in (0, 1, 2, 3):
            part.lod_floor = floor
            if not self.build_part(scene_path, d, part, shrink):
                self.report.warn(f"{cid}: no meshes; skipped")
                return None
            if part.triangles <= spec["lod_budget"]:
                break
        self.report.note(f"{cid}: {part.triangles} triangles at LOD floor {part.lod_floor}, {length:.0f} m x {shrink:.2f}")
        k = shrink * UNITS_PER_METRE
        mounts = [m for m in part.mounts if m["slotType"] in (3, 5)]
        if not any(m["slotType"] == 3 for m in mounts):   # no engine nodes at all: one exhaust at the stern's centre
            mounts.append({"slotType": 3, "position_engine": [0.0, round(float((lo[1] + hi[1]) / 2) * k, 1), round(float(lo[2]) * k, 1)], "socketScale": 2.0})
        turrets, seen = [], set()
        for placed in asm.references + asm.locators:
            n = placed.node.name
            if not TURRET_NODES.search(n) or re.search(r"(joint|rotate|projecttile|missile)", n, re.I):
                continue
            W = placed.matrix
            pos = tuple(round(float(x) * k, 1) for x in W[:3, 3])
            if any(abs(pos[0] - q[0]) + abs(pos[1] - q[1]) + abs(pos[2] - q[2]) < 20 for q in seen):
                continue
            seen.add(pos)
            up = W[:3, 1] / max(np.linalg.norm(W[:3, 1]), 1e-9)
            turrets.append({"slotType": 2, "position_engine": list(pos), "turretUp": [round(float(x), 3) for x in up]})
        turrets.sort(key=lambda m: -abs(m["position_engine"][0]) - abs(m["position_engine"][1]))   # the outermost first: the ones that see most sky
        turrets = turrets[:MAX_TURRETS]
        subsystems = []
        if spec.get("hangar"):
            for placed in asm.locators:
                if HANGAR_NODES.search(placed.node.name):
                    W = placed.matrix
                    fwd = -W[:3, 2] / max(np.linalg.norm(W[:3, 2]), 1e-9)
                    subsystems.append({"kind": "hangar", "model": "none", "position_engine": [round(float(x) * k, 1) for x in W[:3, 3]],
                                       "turretUp": [round(float(x), 3) for x in fwd], "ships": [f"{MOD_ID}:{x}" for x in spec["hangar"]],
                                       "every": 30, "perWave": 2, "maxAlive": 4, "total": 8})
                    break
        backward = faces_backward([part])
        if backward:
            turrets, mounts, subsystems = turn_mounts(turrets), turn_mounts(mounts), turn_mounts(subsystems)
        races = spec["races"]
        entry = {"id": cid, "name": spec["name"], "description": spec["description"], "race": races[0],
                 "armor": 2000 * spec["hull"], "cargo": 0, "handling": 30, "price": 0,
                 "slots": {"primary": 0, "secondary": 0, "turret": len(turrets), "equipment": 0},
                 "model": part.model, "modelLength": round(length * shrink * UNITS_PER_METRE, 1), "modelYaw": 180 if backward else 0,
                 "mounts": turrets + mounts,
                 "npcTurrets": [TURRET_ITEMS[i % len(TURRET_ITEMS)] for i in range(len(turrets))],
                 "traffic": {"capital": spec["kind"], "weight": 1, "races": races},
                 "hullFactor": spec["hull"], "engineStyle": "es2", "explosionScale": 3 if spec["kind"] == "battleship" else 2,
                 "materials": self.materials.ship_entries(part.material_names)}
        if part.engine_colour:
            entry["engineGlowColor"] = part.engine_colour
        if subsystems:
            entry["subsystems"] = subsystems
        return entry

    def write_animations(self, w, anims, glb_nodes, chains, ensure, overrides):
        """The flight loop (the entities' idle loops and the spinning parts) as the GLB's first animation, the
        take-off and landing after it (or as the first, looped, with TRANSITIONS "loop")."""
        def channels_of(tracks, offset=0.0):
            chans = []
            for node, rots, trans, scales in tracks:
                if node not in glb_nodes:
                    if node not in chains:
                        continue   # nothing drawn moves with this node
                    ensure(chains[node])
                n = len(rots or trans or scales)
                times = [offset + k / animation.FPS for k in range(n)]
                if rots:
                    chans.append((glb_nodes[node], "rotation", times, rots))
                if trans:
                    chans.append((glb_nodes[node], "translation", times, trans))
                if scales:
                    chans.append((glb_nodes[node], "scale", times, scales))
            return chans
        flight = channels_of(anims["loop"])
        for node, axis, speed in anims["spins"]:
            if node not in glb_nodes:
                if node not in chains:
                    continue
                ensure(chains[node])
            _, q0, _ = glb.trs(overrides.get(node, node.local))
            period = 1.0 / abs(speed)
            sign = 1.0 if speed > 0 else -1.0
            keys = [(k / 8.0 * period, glb.quaternion_multiply(q0, glb.axis_angle(axis, sign * k / 8.0 * 2 * math.pi))) for k in range(9)]
            flight.append((glb_nodes[node], "rotation", [t for t, _ in keys], [q for _, q in keys]))
        if TRANSITIONS == "loop" and anims["transitions"]:
            chans, offset = [], 0.0
            for kind in ("takeoff", "landing"):
                tracks = anims["transitions"].get(kind)
                if tracks:
                    chans += channels_of(tracks, offset)
                    offset += max(len(r or t or s) for _, r, t, s in tracks) / animation.FPS
            w.add_animation("flight", chans + flight)
        elif flight:
            w.add_animation("flight", flight)
        for kind, tracks in anims["transitions"].items():
            w.add_animation(kind, channels_of(tracks))


# --- per-part stat bonuses --------------------------------------------------------------------------------------------

STAT_LIMIT = 8   # per cent at most, per stat and part: a build stays close to its ship's own numbers
WING_SLOTS = re.compile(r"(wing|sail|tip|flap|skirt|fin)", re.I)
ENGINE_SLOTS = re.compile(r"(engine|thrust)", re.I)
HULL_SLOTS = re.compile(r"(cockpit|hull|body|pit|shuttle|sclassship|back|core|frame|canopy)", re.I)


def part_stats(parts):
    """Small stat bonuses from each part's size against the other parts of its slot, the old No Man's Sky flavour
    (big wings carried more; the game dropped it in 4.0): wings: wider = more cargo, less handling and turn; hulls:
    bigger = more hull and cargo, slower to accelerate, smaller = handling and speed; engines: bigger = faster,
    quicker, less nimble. Accessories and the rest: nothing. Percentages, +-STAT_LIMIT at most."""
    by_slot = {}
    for p in parts:
        if p.bounds:
            by_slot.setdefault(p.slot, []).append(p)
    for slot, group in by_slot.items():
        kind = "wing" if WING_SLOTS.search(slot) else "engine" if ENGINE_SLOTS.search(slot) else "hull" if HULL_SLOTS.search(slot) else None
        if kind is None or len(group) < 2:
            continue

        def measure(p):
            lo, hi = p.bounds
            ext = [max(hi[i] - lo[i], 1e-3) for i in range(3)]
            return ext[0] if kind == "wing" else ext[0] * ext[1] * ext[2]
        values = [measure(p) for p in group]
        mean = sum(values) / len(values)
        for p, v in zip(group, values):
            ratio = max(-1.0, min(1.0, math.log(v / mean) / math.log(2.0)))   # twice the mean = +1, half = -1
            k = round(ratio * STAT_LIMIT)
            if k == 0:
                continue
            if kind == "wing":
                stats = {"cargo": k, "handling": -k // 2, "turnRate": -k // 2}
            elif kind == "hull":
                stats = {"armor": k, "cargo": k * 3 // 4, "acceleration": -k // 2, "handling": -k // 3, "topSpeed": -k // 4}
            else:
                stats = {"topSpeed": k, "acceleration": k, "handling": -k // 2}
            p.stats = {a: b for a, b in stats.items() if b}


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


def faces_backward(parts):
    """Whether the model's nose points -Z: its exhausts sit forward of its hull's centre."""
    ex = [m["position_engine"][2] for p in parts for m in p.mounts if m["slotType"] == 3]
    bounds = [p.bounds for p in parts if p.bounds]
    if not ex or not bounds:
        return False
    lo = min(b[0][2] for b in bounds)
    hi = max(b[1][2] for b in bounds)
    return sum(ex) / len(ex) > (lo + hi) / 2 * UNITS_PER_METRE * (parts[0].scale if hasattr(parts[0], "scale") else 1)


def turn_mounts(mounts):
    """The mounts of a model turned half around (x and z negated, the facings too)."""
    out = []
    for m in mounts:
        m = dict(m)
        x, y, z = m["position_engine"]
        m["position_engine"] = [-x, y, -z]
        for key in ("turretUp", "rotation"):
            if key in m and isinstance(m[key], list) and len(m[key]) == 3:
                m[key] = [-m[key][0], m[key][1], -m[key][2]]
        out.append(m)
    return out


def ship_entry(kit, name, spec, parts):
    build = {}
    for slot in kit["slots"]:
        first = next((p for p in parts if p.slot == slot), None)
        if first:
            build[slot] = first.id
    chosen = [p for p in parts if p.id in build.values()]
    primaries = sum(1 for p in chosen for m in p.mounts if m["slotType"] == 0)
    secondaries = sum(1 for p in chosen for m in p.mounts if m["slotType"] == 1)
    exhausts = sum(1 for p in chosen for m in p.mounts if m["slotType"] == 3)
    build["colors"] = dict(DEFAULT_COLORS)
    entry = {"id": kit["id"], "name": name, "description": spec["description"], "race": 0,
             "armor": spec["armor"], "cargo": spec["cargo"], "handling": spec["handling"], "price": spec["price"],
             "slots": {"primary": max(2, min(primaries, 6)), "secondary": max(2, min(secondaries, 4)), "turret": 0, "equipment": spec["equipment"]},
             "kit": kit["id"], "kitType": kit["id"], "build": build,
             "engineGlowColor": next((p.engine_colour for p in chosen if p.engine_colour), [0.62, 0.16, 1.0]),
             "dealer": {"chance": 3 if "proc" in spec else 1, "systemRace": -1, "minTechLevel": 3 if "proc" in spec else 6},
             "lounge": {"systemRace": -1, "minCampaign": 8, "minRank": 4, "chance": 10 if "proc" in spec else 4}}
    if spec.get("race") is not None:
        entry["race"] = spec["race"]
    if spec.get("traffic_only"):   # a hostile craft of the traffic: flown by its race's fighters, never sold
        del entry["dealer"], entry["lounge"]
        entry["traffic"] = {"weight": 1, "races": [spec["race"]]}
    else:
        class_id = kit["id"].split("-")[0]   # "shuttle_double-boxdouble" -> "shuttle_double" -> "shuttle"
        races, weight = TRAFFIC.get(class_id) or TRAFFIC.get(class_id.split("_")[0]) or FIXED_TRAFFIC
        entry["traffic"] = {"weight": weight, "races": races}
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
    """Builds the mod: `classes` names ship classes (CLASSES), capital ships (CAPITALS), station models (world.STATIONS)
    and weapons (weapons.WEAPONS), or the words "stations" / "weapons" for all of them. Returns (kits, ships, report);
    the report's `extras` holds the systems, stations and items written."""
    import weapons as weapons_mod
    import world
    report = report or Report()
    t0 = time.time()
    classes = list(classes) if classes else list(CLASSES)
    os.makedirs(out, exist_ok=True)
    kb = KitBuilder(banks, out, report, MAX_VARIANTS, MAX_PARTS_PER_SLOT)
    kits, ships = [], []
    capitals = [c for c in classes if c in CAPITALS]
    station_ids = [c for c in classes if c in world.STATIONS] + (list(world.STATIONS) if "stations" in classes else [])
    weapon_ids = [c for c in classes if c in {w["id"] for w in weapons_mod.WEAPONS}] + ([w["id"] for w in weapons_mod.WEAPONS] if "weapons" in classes else [])
    classes = [c for c in classes if c in CLASSES]
    for class_id in classes:
        spec = CLASSES[class_id]
        log(f"{spec['name']} ({scene_file(spec.get('proc') or spec.get('scene'))})")
        for kit, name, parts in kb.build_class(class_id, spec, limit_parts):
            pal, slots, presets = colour_slots()
            kit["palettes"], kit["colorSlots"], kit["presets"] = pal, slots, presets
            kits.append(kit)
            ships.append(ship_entry(kit, name, spec, parts))
            tris = sum(p.triangles for p in parts)
            log(f"  {kit['id']}: {len(parts)} parts, {tris} triangles ({time.time() - t0:.0f} s)")
    for cid in capitals:
        spec = CAPITALS[cid]
        log(f"{spec['name']} ({scene_file(spec['scene'])})")
        entry = kb.build_capital(cid, spec)
        if entry:
            ships.append(entry)
            log(f"  {cid}: {entry['modelLength'] / UNITS_PER_METRE:.0f} m, {len([m for m in entry['mounts'] if m['slotType'] == 2])} turrets, "
                f"{len([m for m in entry['mounts'] if m['slotType'] == 3])} exhausts ({time.time() - t0:.0f} s)")
    systems, stations, items = [], [], []
    if station_ids:
        systems, stations, _ = world.build_world(kb, station_ids)
        log(f"  {len(stations)} stations in {len(systems)} systems ({time.time() - t0:.0f} s)")
    if weapon_ids:
        log("Weapons...")
        from nms import tables
        tech = tables.technologies(banks.read(tables.TECH_TABLE)) if banks.exists(tables.TECH_TABLE) else {}
        if not tech:
            report.warn(f"{tables.TECH_TABLE} is missing or unreadable: no weapons")
        else:
            texts = tables.english(banks.read(f) for f in tables.english_files(banks))
            items = weapons_mod.build_weapons(banks, out, report, texts, tech, weapon_ids)
            log(f"  {len(items)} weapons ({time.time() - t0:.0f} s)")
    if SOUNDS and (ships or items):
        import sounds as sounds_mod
        log("Sounds...")
        n = sounds_mod.apply(banks, out, report, ships, items)
        if n >= 0:
            log(f"  {n} sound files ({time.time() - t0:.0f} s)")
    log("Textures...")
    done, failed = kb.materials.convert(out, max_texture)
    log(f"  {done} written" + (f", {failed} failed" if failed else ""))
    for kit in kits:
        kit["materials"] = kb.materials.kit_entries()
    if kits or ships or not (systems or items):
        write_json(os.path.join(out, "shipkits.json"), kits)
        write_json(os.path.join(out, "ships.json"), ships)
    if systems:
        write_json(os.path.join(out, "systems.json"), systems)
        write_json(os.path.join(out, "stations.json"), stations)
    if items:
        write_json(os.path.join(out, "items.json"), items)
    report.extras = {"systems": systems, "stations": stations, "items": items}
    sold = sorted({s["name"] for s in ships if "kit" in s and "dealer" in s})
    hostile = sorted({s["name"] for s in ships if "kit" in s and "dealer" not in s})
    capital = sorted({s["name"] for s in ships if "kit" not in s})
    parts = ["No Man's Sky's starships as customizable hulls: " + ", ".join(sold)] if sold else []
    if hostile:
        parts.append("its sentinel craft and drones as hostile fighters: " + ", ".join(hostile))
    if capital:
        parts.append("its freighters, frigates and dreadnoughts in the orbits' traffic: " + ", ".join(capital))
    if systems:
        parts.append(f"{len(systems)} systems of its own with its space stations, derelict freighters and the Anomaly: " + ", ".join(s["name"] for s in systems))
    if items:
        parts.append("its ship weapons in the shops: " + ", ".join(i["name"]["en"] for i in items))
    write_json(os.path.join(out, "mod.json"), {
        "id": MOD_ID, "name": "No Man's Sky ships", "version": VERSION, "author": "built by nms_ships_importer",
        "description": "; ".join(parts) + ". Built on this device from your own copy of No Man's Sky.",
        "credits": "Models, textures and numbers: No Man's Sky (c) Hello Games, from the player's own copy of the game. For personal use: don't share the built mod.",
        "multiplayerIgnore": ["parts/", "maps/", "models/", "fx/", "audio/"]})
    if report.missing_textures:
        report.warn(f"{len(report.missing_textures)} textures named by materials are not in the archives (e.g. {report.missing_textures[0]})")
    log(f"Done in {time.time() - t0:.0f} s: {len(kits)} kits, {sum(len(k['parts']) for k in kits)} parts, {len(stations)} stations, {len(items)} weapons -> {out}")
    return kits, ships, report


def zip_mod(out, zip_path):
    base = os.path.splitext(zip_path)[0]
    shutil.make_archive(base, "zip", os.path.dirname(out), os.path.basename(out))
    return base + ".zip"
