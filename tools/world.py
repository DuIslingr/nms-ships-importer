"""The mod's world: No Man's Sky's space stations, derelict freighters and other space structures as the remake's
stations (stations.json), in a cluster of star systems of their own (systems.json) named after the game's galaxies.

A station model is one GLB from its scene: the game's stations are built like its ships, a descriptor picking the
shape (`_Station_Cub` / `_Ico` / `_Oct` / `_Tet` / `_Sphere`; the newer type B's `_Type_Tet` / `_Disk` / `_EX` ...)
and the interior hanging under it as a separate subtree, so `keep` names the exterior's subtree and each shape is
built as its own model with that option forced. The derelicts and the outpost carry their interiors in the same
subtrees as their hulls (the gore in an open habitat, the shop in the outpost), and those have no LODs: past LOD
floor 1 the mesh families without LODs are dropped, which leaves the hulls. The model is turned so its docking tunnel faces +Z (the remake
launches ships along the station's front and arrivals come from there), a turn baked into the GLB, not left to the
station's `modelYaw`, so the glTF importer's X flip can't undo it. Big stations are shrunk to the remake's 5 km
(the type B stations are 9.5 km across in the game), small structures (the derelicts, 100-230 m) are scaled up
like the ships (x3.5), so they keep their size against them.
"""
import math
import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

STATION_SCALE = 3.5          # the derelicts, wrecks and drones: the ships' own scale, so they keep their size against them
MAX_STATION_UNITS = 100000   # the remake's biggest original station (5 km); bigger models are shrunk to it
UNITS_PER_METRE = 20.0
FRONT_NODES = re.compile(r"(tunnelopening|_tunnelopeningref_|approach|maintunnel|mainentrance)", re.I)

# `scene` from the archive root (without .scene.mbin), `keep` the subtree drawn, `picks` the descriptor options forced,
# `lod_budget` the triangles allowed, `scale` a size factor, `front` where the docking tunnel is (default FRONT_NODES)
STATIONS = {
    "station_cube": dict(scene="models/space/spacestation/spacestation", name="Space Station (cube)", picks=["_Station_Cub"], keep=r"/_?Outside_", lod_budget=300000),
    "station_ico": dict(scene="models/space/spacestation/spacestation", name="Space Station (icosahedron)", picks=["_Station_Ico"], keep=r"/_?Outside_", lod_budget=300000),
    "station_oct": dict(scene="models/space/spacestation/spacestation", name="Space Station (octahedron)", picks=["_Station_Oct"], keep=r"/_?Outside_", lod_budget=300000),
    "station_tet": dict(scene="models/space/spacestation/spacestation", name="Space Station (tetrahedron)", picks=["_Station_Tet"], keep=r"/_?Outside_", lod_budget=300000),
    "station_sphere": dict(scene="models/space/spacestation/spacestation", name="Space Station (sphere)", picks=["_Station_Sphere"], keep=r"/_?Outside_", lod_budget=300000),
    "pirate_station": dict(scene="models/space/spacestation/spacestation_pirate", name="Outlaw Station", picks=["_Station_Cub"], keep=r"/_?Outside_", lod_budget=300000),
    "abandoned_station": dict(scene="models/space/spacestation/spacestation_abandoned", name="Abandoned Station", picks=["_Station_Oct"], keep=r"/_?Outside_", lod_budget=300000),
    # the type B's ExtBuildRing is the game's base-building limit, a 9 km ring of light: not a part of the station
    "station_b_tet": dict(scene="models/space/spacestation/spacestationtypeb_exterior", name="Orbital Station (towers)", picks=["_Type_Tet"], lod_budget=400000, skip=r"extbuildring"),
    "station_b_disk": dict(scene="models/space/spacestation/spacestationtypeb_exterior", name="Orbital Station (disk)", picks=["_Type_Disk"], lod_budget=400000, skip=r"extbuildring"),
    "station_b_ex": dict(scene="models/space/spacestation/spacestationtypeb_exterior", name="Orbital Station (cross)", picks=["_Type_EX"], lod_budget=400000, skip=r"extbuildring"),
    "anomaly": dict(scene="models/space/anomaly/anomaly", name="Space Anomaly", keep=r"/(Exterior\d*|OuterRing\d*|ExteriorLighting|polySurface151)(/|$)", lod_budget=200000, scale=2.0),
    "atlas_station": dict(scene="models/space/atlasstation/atlasstation_exterior", name="Atlas Interface", lod_budget=200000, skip=r"corridorshadow"),
    "outpost": dict(scene="models/space/poi/outpost/outpost", name="Trading Outpost", lod_budget=300000, scale=2.0),
    "derelict_a": dict(scene="models/space/poi/hulk/hulkstructure01", name="Derelict Freighter", lod_budget=450000, scale=STATION_SCALE),
    "derelict_b": dict(scene="models/space/poi/hulk/hulkstructure02", name="Derelict Freighter", lod_budget=450000, scale=STATION_SCALE),
    "derelict_c": dict(scene="models/space/poi/hulk/hulkstructure03", name="Derelict Freighter", lod_budget=450000, scale=STATION_SCALE),
    "derelict_d": dict(scene="models/space/poi/hulk/hulkstructure04", name="Derelict Freighter", lod_budget=450000, scale=STATION_SCALE),
    "derelict_e": dict(scene="models/space/poi/hulk/hulkstructure05", name="Derelict Freighter", lod_budget=450000, scale=STATION_SCALE),
    "derelict_f": dict(scene="models/space/poi/hulk/hulkstructure07", name="Derelict Freighter", lod_budget=450000, scale=STATION_SCALE),
    "wreck": dict(scene="models/space/poi/spacedebris", name="Starship Wreck", lod_budget=200000, scale=STATION_SCALE),
    "gate": dict(scene="models/space/poi/gate_poi", name="Portal", lod_budget=150000),
}

# the systems: a cluster in the star map's far top corner, next to Me'enkk and Alda, each with its stations (an
# orbit each, the first the gate orbit): `model` a STATIONS entry, `dock` False for a structure flown past
SYSTEMS = [
    dict(id="euclid", name="Euclid", race=0, security=2, position=[85, 90, 80], sky=1, gates=[30, 33, "hilbert", "calypso"],
         stations=[dict(id="euclid_station", model="station_cube", name="Euclid Station", techLevel=6, planet=2, subtitle="Space Station",
                        description="A No Man's Sky space station: a hollow polyhedron with a docking tunnel, the traders' hub of Euclid."),
                   dict(id="euclid_outpost", model="outpost", name="Euclid Trading Post", techLevel=4, planet=5, subtitle="Trading Outpost",
                        description="A small No Man's Sky space outpost with a shop and landing pads."),
                   dict(id="euclid_derelict", model="derelict_a", name="Derelict Freighter", planet=9, dock=False, subtitle="Derelict",
                        description="A dead freighter adrift: gantries, habitation modules and a cold reactor. Nothing answers."),
                   dict(id="euclid_wreck", model="wreck", name="Starship Wreck", planet=12, dock=False, subtitle="Wreck",
                        description="The remains of a starship, broken among the rocks.")]),
    dict(id="hilbert", name="Hilbert Dimension", race=2, security=3, position=[93, 86, 86], sky=4, gates=["hesperius", "eissentam"],
         stations=[dict(id="hilbert_station", model="station_b_tet", name="Hilbert Orbital", techLevel=8, planet=1, subtitle="Orbital Station",
                        description="A No Man's Sky orbital station of the newer build: towers, rings and a wide docking tunnel."),
                   dict(id="hilbert_station_2", model="station_ico", name="Hilbert Station", techLevel=5, planet=7, subtitle="Space Station",
                        description="A No Man's Sky space station, icosahedral, the second station of Hilbert."),
                   dict(id="hilbert_derelict", model="derelict_b", name="Derelict Freighter", planet=10, dock=False, subtitle="Derelict",
                        description="A derelict freighter, its modules open to space."),
                   dict(id="hilbert_atlas", model="atlas_station", name="Atlas Interface", planet=15, dock=False, subtitle="Atlas Interface",
                        description="The Atlas's own station: a red-lit interface hanging in the dark. It does not take ships.")]),
    dict(id="calypso", name="Calypso", race=1, security=1, position=[90, 95, 74], sky=6, gates=["hyades"],
         stations=[dict(id="calypso_station", model="station_oct", name="Calypso Station", techLevel=7, planet=3, subtitle="Space Station",
                        description="A No Man's Sky space station, octahedral, under Vossk law."),
                   dict(id="calypso_derelict", model="derelict_c", name="Derelict Freighter", planet=8, dock=False, subtitle="Derelict",
                        description="A derelict freighter: a maze of gantries and sealed habitats."),
                   dict(id="calypso_derelict_2", model="derelict_d", name="Derelict Freighter", planet=16, dock=False, subtitle="Derelict",
                        description="A small derelict, broken in two."),
                   dict(id="calypso_abandoned", model="abandoned_station", name="Abandoned Station", planet=14, dock=False, subtitle="Abandoned",
                        description="A No Man's Sky space station left to the dark: no lights, no docking.")]),
    dict(id="hesperius", name="Hesperius Dimension", race=3, security=2, position=[97, 92, 82], sky=8, gates=["eissentam"],
         stations=[dict(id="hesperius_station", model="station_tet", name="Hesperius Station", techLevel=6, planet=4, subtitle="Space Station",
                        description="A No Man's Sky space station, tetrahedral, the Midorians' foothold here."),
                   dict(id="hesperius_orbital", model="station_b_disk", name="Hesperius Orbital", techLevel=9, planet=10, subtitle="Orbital Station",
                        description="A No Man's Sky orbital station of the disk build."),
                   dict(id="hesperius_derelict", model="derelict_e", name="Derelict Freighter", planet=18, dock=False, subtitle="Derelict",
                        description="A derelict freighter, dark and silent.")]),
    dict(id="hyades", name="Hyades", race=0, security=0, position=[88, 83, 92], sky=12, gates=[],
         stations=[dict(id="hyades_station", model="pirate_station", name="Hyades Outlaw Station", techLevel=8, planet=17, subtitle="Outlaw Station",
                        description="A No Man's Sky outlaw station: the pirates' own market, no questions asked."),
                   dict(id="hyades_derelict", model="derelict_f", name="Derelict Freighter", planet=0, dock=False, subtitle="Derelict",
                        description="A derelict freighter picked over by the outlaws."),
                   dict(id="hyades_wreck", model="wreck", name="Starship Wreck", planet=19, dock=False, subtitle="Wreck",
                        description="A wreck the outlaws left behind.")]),
    dict(id="eissentam", name="Eissentam", race=2, security=3, position=[96, 97, 90], sky=16, gates=[],
         stations=[dict(id="eissentam_station", model="station_sphere", name="Eissentam Station", techLevel=10, planet=6, subtitle="Space Station",
                        description="A No Man's Sky space station, spherical, the richest market of the cluster."),
                   dict(id="eissentam_orbital", model="station_b_ex", name="Eissentam Orbital", techLevel=9, planet=11, subtitle="Orbital Station",
                        description="A No Man's Sky orbital station of the cross build."),
                   dict(id="eissentam_outpost", model="outpost", name="Eissentam Trading Post", techLevel=5, planet=13, subtitle="Trading Outpost",
                        description="A small No Man's Sky space outpost.")]),
]
ANOMALY = dict(id="space_anomaly", model="anomaly", name="Space Anomaly", techLevel=10, planet=20, system="euclid", subtitle="The Anomaly",
               description="No Man's Sky's Space Anomaly: a sphere of unknown make that moves from system to system, and takes any ship in.",
               mobile=dict(route="any", stayMinutes=20, systemMinutes=120, speed=0.15, race="terran"))


def force_picks(d, picks, wanted):
    """`picks` (lower-case option ids, as descriptors.default_picks makes them) with each option named in `wanted`
    chosen in its group: the group's other options dropped, the wanted one's id and its nested defaults added."""
    from nms import descriptors
    wanted = {w.lower() for w in wanted}

    def walk(groups):
        for g in groups:
            hit = [o for o in g.options if o.name.lower() in wanted or o.id.lower() in wanted]
            if hit:
                for o in g.options:
                    picks.discard(o.id.lower())
                    picks.discard(o.name.lower())
                picks.add(hit[0].id.lower())
                for sub in hit[0].groups:
                    descriptors.default_picks(sub, picks)
            for o in g.options:
                walk(o.groups)
    walk(d.groups)
    return picks


def yaw_matrix(angle):
    """A 4x4 rotation about Y by `angle` radians."""
    c, s = math.cos(angle), math.sin(angle)
    M = np.identity(4)
    M[0, 0], M[0, 2], M[2, 0], M[2, 2] = c, s, -s, c
    return M


def front_direction(asm, keep, centre):
    """The direction (x, z) from the model's centre to its docking tunnel: the mean of the positions of the nodes
    named like one (and of the meshes under such a node), or None."""
    pts = []
    for p in asm.locators + asm.references:
        if FRONT_NODES.search(p.node.name):
            pts.append(p.matrix[:3, 3])
    if not pts:
        for p in asm.meshes:
            if FRONT_NODES.search(p.path) and (keep is None or keep.search(p.path)):
                pts.append(p.matrix[:3, 3])
    if not pts:
        return None
    d = np.mean(pts, axis=0) - centre
    return (float(d[0]), float(d[2])) if abs(d[0]) + abs(d[2]) > 1.0 else None


def build_station(kb, sid, spec):
    """One station model from its scene: the exterior subtree (`keep`), its shape forced (`picks`), turned to face
    its docking tunnel along +Z, coarser LODs until it fits its triangle budget, scaled. Returns the model's
    (path, size in game units, materials entries) or None."""
    from nms import descriptors, geometry, scene
    import build
    scene_path = spec["scene"] + ".scene.mbin"
    if not kb.banks.exists(scene_path):
        kb.report.warn(f"{sid}: {scene_path} is not in the archives; skipped")
        return None
    desc_path = spec["scene"] + ".descriptor.mbin"
    d, picks = None, set()
    if kb.banks.exists(desc_path):
        d = descriptors.Descriptor(kb.banks.read(desc_path))
        for g in d.groups:
            descriptors.default_picks(g, picks)
        if spec.get("picks"):
            force_picks(d, picks, spec["picks"])
    keep = re.compile(spec["keep"], re.I) if spec.get("keep") else None
    skip = re.compile(spec["skip"], re.I) if spec.get("skip") else None
    # a first pass for the size and the tunnel's direction
    asm = scene.Assembler(kb.banks, descriptors.chooser(d, picks) if d else None, pick=kb.pick)
    asm.assemble(scene_path)
    drawn = [p for p in asm.meshes if not build.SKIP_NODES.search(p.path) and (keep is None or keep.search(p.path)) and not (skip and skip.search(p.path))]
    lo, hi = np.array([1e9] * 3), np.array([-1e9] * 3)
    for placed in scene.finest_meshes(drawn):
        m = placed.scene.geometry.mesh(placed.node.name)
        if len(m.indices):
            pos = geometry.apply(placed.matrix, m.positions)
            lo, hi = np.minimum(lo, pos.min(0)), np.maximum(hi, pos.max(0))
    if hi[0] < lo[0]:
        kb.report.warn(f"{sid}: no meshes under {spec.get('keep') or 'the scene'}; skipped")
        return None
    centre = (lo + hi) / 2
    extent = float((hi - lo).max())
    scale = spec.get("scale", 1.0) * min(1.0, MAX_STATION_UNITS / (extent * spec.get("scale", 1.0) * UNITS_PER_METRE))
    frame = np.identity(4)
    front = front_direction(asm, keep, centre)
    if front is not None:
        frame = yaw_matrix(-math.atan2(front[0], front[1]))   # the tunnel's direction turned onto +Z
    part = build.Part(sid, "hull", spec["name"], None, picks)
    part.model = f"models/{sid}.glb"
    part.keep, part.skip, part.frame = keep, skip, frame
    part.drop_detail = True
    for floor in (0, 1, 2, 3):
        part.lod_floor = floor
        if not kb.build_part(scene_path, d, part, scale):
            kb.report.warn(f"{sid}: no meshes; skipped")
            return None
        if part.triangles <= spec["lod_budget"]:
            break
    size = round(extent * scale * UNITS_PER_METRE, 1)
    kb.report.note(f"{sid}: {part.triangles} triangles at LOD floor {part.lod_floor}, {extent:.0f} m x {scale:.2f}" + (", turned to its tunnel" if front else ""))
    return part.model, size, kb.materials.ship_entries(part.material_names)


def station_entry(inst, model, size, materials, system_id, mod_id):
    e = {"id": inst["id"], "name": inst["name"], "subtitle": inst.get("subtitle", ""), "description": inst.get("description", ""),
         "system": f"{mod_id}:{system_id}", "techLevel": inst.get("techLevel", 1), "planet": inst.get("planet", 0),
         "model": model, "modelSize": size, "collision": "box", "materials": materials}
    if inst.get("dock", True) is False:
        e["orbit"] = {"station": "nodock"}
    if inst.get("mobile"):
        e["mobile"] = dict(inst["mobile"])
    return e


def build_world(kb, which=None):
    """The stations' models and the systems' and stations' entries. `which` limits the STATIONS built (None: all);
    the systems' entries only name the stations whose models were built. Returns (systems, stations, models)."""
    which = set(STATIONS) if which is None else set(which)
    models = {}
    for sid in STATIONS:
        if sid not in which:
            continue
        build_log(f"{STATIONS[sid]['name']} ({STATIONS[sid]['scene']})")
        built = build_station(kb, sid, STATIONS[sid])
        if built:
            models[sid] = built
            build_log(f"  {sid}: {built[1] / UNITS_PER_METRE:.0f} m")
    mod_id = build_mod_id()
    systems, stations = [], []
    for sy in SYSTEMS:
        entry = {"id": sy["id"], "name": sy["name"], "race": sy["race"], "security": sy["security"], "visible": True,
                 "position": sy["position"], "sky": sy["sky"], "traffic": "mod",
                 "gates": [g if isinstance(g, int) else f"{mod_id}:{g}" for g in sy["gates"]]}
        if "gate" in models:
            model, size, mats = models["gate"]
            entry["jumpgate"] = {"model": model, "size": size, "radius": round(size * 0.45, 1), "materials": mats}
        mine = []
        for inst in sy["stations"]:
            if inst["model"] in models:
                model, size, mats = models[inst["model"]]
                mine.append(station_entry(inst, model, size, mats, sy["id"], mod_id))
        if not mine:
            continue
        if mine[0].get("orbit", {}).get("station") == "nodock":   # the gate orbit must hold a station to dock at
            dockable = next((s for s in mine if "orbit" not in s), None)
            if dockable:
                mine.remove(dockable)
                mine.insert(0, dockable)
        entry["gateStation"] = f"{mod_id}:{mine[0]['id']}"
        systems.append(entry)
        stations.extend(mine)
    if "anomaly" in models and any(s["id"] == ANOMALY["system"] for s in systems):
        model, size, mats = models["anomaly"]
        stations.append(station_entry(ANOMALY, model, size, mats, ANOMALY["system"], mod_id))
    return systems, stations, models


def build_log(msg):
    import build
    build.log(msg)


def build_mod_id():
    import build
    return build.MOD_ID
