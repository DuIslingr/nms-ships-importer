# No Man's Sky ships importer

Builds the **nms_ships** mod for the Galaxy on Fire 2 Unity Remake from **your own copy of No Man's Sky**: its
starship classes as customizable ships you put together in the hangar from No Man's Sky's own parts (the fighters'
cockpits, engines and wings with their accessories and noses; the haulers' cockpits and hulls with their wings and
engines; the explorers' frames; the shuttles' modular hulls; the exotics' royal and squid hulls; the solar sails; the
sentinel interceptors), painted in your colours, with the game's own weapon and exhaust positions.

This importer contains **nothing from No Man's Sky**: no models, textures or game data, only the readers and the scripts
that convert the files of your own installation. The mod it builds does contain No Man's Sky's models and textures
(© Hello Games), so it is for your own use: **don't share or upload the built mod**. Share this importer instead.

## What you need

The importer runs on **Windows, macOS and Linux** and reads the game's archives itself: no FModel, no MBINCompiler, no
unpacking first.

- A version of the **Galaxy on Fire 2 Unity Remake** with customizable ships (the hangar's *Customize ship* button).
- **No Man's Sky**, installed: the PC game (Steam, GOG, the Microsoft Store), whose files are `GAMEDATA/PCBANKS` in the
  game folder, or the **iOS game's** app folder (its `GAMEDATA/IOSBANKS`). Both archive layouts are read: the PC
  archives on Windows and Linux are Zstandard-compressed, the macOS game's LZ4, the iOS game's Oodle (see below).
- **Python 3.9 or newer** with numpy and Pillow:
  - Windows: install Python from python.org (tick "Add python.exe to PATH"), then in a Command Prompt
    `py -m pip install numpy pillow`
  - macOS: install Python from python.org or Homebrew (`brew install python`), then in Terminal
    `python3 -m pip install numpy pillow`
  - Linux: your distribution's `python3`, `python3-numpy` and `python3-pil` (or `python3 -m pip install numpy pillow`)
- For the archives' compression, by where your game comes from:
  - **PC on Windows / Linux** (Zstandard): nothing more with **Python 3.14** or newer; on an older Python
    `python3 -m pip install zstandard`.
  - **PC on macOS** (LZ4): `python3 -m pip install lz4`.
  - **iOS** (Oodle Kraken): `python3 -m pip install pyooz` (the open-source ooz decoder). The iOS textures are ASTC,
    which Pillow can't read: install `python3 -m pip install astc_decomp_faster` too, or put ARM's `astcenc` on the
    PATH; without one the iOS build gets its models but no textures (the importer says so).
  The importer tells you which package it needs when an archive asks for it. The iOS game's models are lighter than
  the PC game's (its big hulls keep a coarser mesh as their finest), so a mod built from the iOS archives is a smaller,
  phone-friendly build of the same ships.

## Building the mod

```
python3 import.py "<the game folder>"
```

(`py import.py ...` on Windows.) The iOS game's `GAMEDATA/IOSBANKS` works the same way; its textures are ASTC, which `astcenc` on the PATH (Arch: `astcenc` in `astc-encoder`) or the `astc_decomp_faster` package decodes. For the sounds, put `vgmstream-cli` on the PATH first (see Sounds below). The game folder is the one holding `GAMEDATA` (Steam: `.../steamapps/common/No Man's Sky`);
the `PCBANKS` or `IOSBANKS` folder itself works too. The mod is written to `nms_ships` next to `import.py` (`--out` for
elsewhere; `--zip` also zips it). A build of everything takes four or five minutes.

| Option | |
|---|---|
| `--classes fighter,hauler` | Only these (`--list-classes` shows the names: the ship classes, the fixed designs, the hostile craft, the capital ships, the station models and the weapons; `procedural` / `fixed` / `hostile` / `capitals` / `stations` / `weapons` for those groups, mixed as you like: `fighter,stations`). Default: all. |
| `--max-parts N` | Parts per slot at most (default 14): the fighters have ten wings, the shuttles dozens of hull pieces. |
| `--max-variants N` | Variants of one part over its nested accessories (default 4): `Wings F`, `Wings F (Acc A3)` ... |
| `--max-texture N` | The textures' longest side (default 2048; 1024 for phones). |
| `--limit-parts N` | A quick test build with N parts per slot. |
| `--fresh` | Delete the output folder first. |
| `--no-sounds` | No engine, boost and weapon sounds (they need `vgmstream-cli` or `ww2ogg` on the PATH, see Sounds below). |
| `--verbose` | Print the build's notes: triangle counts, LOD floors, which models were turned. |
| `--config file` | Settings as JSON; `config.json` next to `import.py` is read by itself (copy `config.example.json`). |

Put the built `nms_ships` folder (or its zip) in the remake's mods folder (the game's Settings > Mods page says where)
and turn it on. The ships are sold by the ordinary ship dealers now and then (from tech level 3) and in the Space
Lounges; in the hangar, **Customize ship** under Inspect ship opens the parts and colours. The No Man's Sky systems
lie in the star map's far corner past Me'enkk and Alda, reached through Euclid's jumpgate; the weapons are in the
shops from tech level 3.

## What the mod holds

One kit per No Man's Sky class, or per hull where a class begins with a whole-hull choice:

| Kit | Slots | From |
|---|---|---|
| Fighter | cockpit, engine, wings (with their accessories and noses as variants) | `FIGHTERS/FIGHTER_PROC` |
| Hauler | cockpit, hull (its wings and engines as variants) | `DROPSHIPS/DROPSHIP_PROC` |
| Explorer (two frames) | the frame, its cockpit, front accessory, back, wings / rear wings | `SCIENTIFIC/SCIENTIFIC_PROC` |
| Shuttle (four hulls) | the hull chain, its cockpit, hull segments, wings, accessories | `SHUTTLE/SHUTTLE_PROC` |
| Exotic (royal, squid) | the hull; the royal's engine, wings, cockpit, top wing | `S-CLASS/S-CLASS_PROC` |
| Solar | tips, wings, body, sails | `SAILSHIP/SAILSHIP_PROC` |
| Sentinel Interceptor | base (its guns), pit, top flap, wings, skirt | `SENTINELSHIP/SENTINELSHIP_PROC` |
| Living Ship | base, top, top accessory, feet, cockpits, engine, wings | `S-CLASS/BIOPARTS/BIOSHIP_PROC` |

And the game's fixed designs, each a kit of one hull (so it takes the paint slots like the others): the Golden Vector
and the gold Rasamama (the classic fighters, `FIGHTERS/FIGHTERCLASSICGOLD`, `RASAMAMAGOLD`), the Utopia Speeder
(`VRSPEEDER`), the Starborn Runner (`VINTAGEINTERCEPTOR`), the two racers (`WRACER`, `WRACERSE`), the Boundary Herald
(`SPOOKSHIP`, the disc with the glowing feather wings), the grown Bio Fighter (`S-CLASS/BIOPARTS/BIOFIGHTER`) and the
Horizon Vector NX (`FIGHTERSPECIALSWITCH`, the special-edition fighter). They
are rarer at the dealers. `--classes fixed` builds only these, `--classes procedural` only the customizable classes; the
names are the importer's (`CLASSES` in `tools/build.py` renames them). The modular corvettes of the Voyagers update are a
different system (a hull built from `BIGGS/MODULES` pieces) and are not brought over.

Each kit's ship (ships.json) has the class's look in stats: fighters fast and lightly loaded, haulers slow with a big
hold, exotics the best handling. Their guns sit where No Man's Sky puts them (the wings' gun references), their exhausts
at the thrusters, with the engine light's colour. Five colour slots (primary, secondary and tertiary paint: No Man's
Sky's own paint materials; lights; engines) with a palette of fourteen paints and seven light colours, and five preset
schemes. The parts keep No Man's Sky's materials: base colour, the masks map as metallic / smoothness, the normal map,
glows as emission. Landing gear and pads, engine jets (the remake draws its own flames) and decals are left out. The shuttles' materials name an overlay normal map the game doesn't ship; their hull's base normal map stands in for it.

Every part is the whole of its option: a wing with the accessory and nose that No Man's Sky's likeliest choice gives
it, as one piece; the other choices are further parts of the slot (up to `--max-variants`). A class is one ship type,
so every part of a kit fits every build of it. No Man's Sky's one ship gun model stays on the hull at the game's gun
points, as the base game's ships carry theirs; the weapon mounts sit at the same points, so your shots leave its barrels,
missiles too (No Man's Sky has no second weapon class: its rockets fire from the same two gun points).

**Capital ships.** The game's big hulls fly in the remake's traffic as capital ships (`ships.json` entries with
`traffic.capital`). As freighters cruising the orbits: the freighter, the small and light freighters, the early
freighter hull and the freight ship, the small transport, the five frigates (combat, science, diplomatic, industrial,
support), the living frigate, the Normandy SR1 and the ghost frigate. As battleships: the capital freighter, parked in
the capital-ship special; the pirate dreadnought and the pirate cruiser (hostile, raiders launching from the
dreadnought's hangar); the sentinel capital ship, the brood frigate and the brood hive (hostile, Void). Each is one
model from its scene (the descriptor's likeliest choices; a frigate's hull is its LOD0 scene with the engine trails of
its base scene), coarser detail levels where a model has them and runs over its triangle budget, shrunk to at most a
few kilometres, with up to eight of the game's turret points as turret mounts armed with the game's blaster turrets,
its engine trails or engine references as exhausts drawn in EVERSPACE 2's style, and its hangar root as a launch point.
The game's big ships face the other way from its fighters: a model whose exhausts sit forward of its centre is turned
half around (`modelYaw` 180, its mounts with it). The sentinel police ship, the sentinel drone ship and the brood
fighter and drone come over as hostile fighters of the traffic, never sold. Left out: the shield spheres, effect planes,
gravity volumes and corvette docking pads the scenes carry, and the modular corvettes. `--classes capitals` builds only
the capital ships.

**Who flies them.** No Man's Sky has no separate hostile fighters: its pirates fly the ordinary ships and its sentinels
their interceptors. So every ship here is also traffic for the remake's NPC fighters (patrols, raiders, pirates, escorts,
guards; the Gameplay option "Mod ships in traffic" sets the share): the fighters, haulers and shuttles for the four trader
races and the pirates, the explorers, exotics, solar and living ships and the fixed designs for the trader races, the
sentinel interceptors, police and drone ships and the brood craft for the Void. The sentinel capital ship, the brood
frigate and hive, the pirate dreadnought and the pirate cruiser are their hostile capital ships.

**Hostile craft.** The sentinels' drones from the game's robots folder fly for the Void as small hostile craft, never
sold: the sentinel drone, the armoured drone, the summoner, the corrupted drone, the repair drone, the cargo scan drone
and the derelict freighters' security drone, with the police ship, the drone ship and the brood fighter and drone from
the spacecraft folder. They are built like the fixed designs (their critical-hit meshes and their patrol and
investigate eyes left out, the attack eye kept; the sentinel drones look along -Z and are turned round) and keep their
idle loops. `--classes hostile` builds only these.

**Stations and systems.** The game's space structures become the remake's stations (`stations.json`), in six star
systems of their own (`systems.json`) named after the game's galaxies (Euclid, Hilbert Dimension, Calypso, Hesperius
Dimension, Hyades, Eissentam), a cluster in the star map's far corner next to Me'enkk and Alda, reached through Euclid's
jumpgate; only the mods' ships fly there. The space station in its five shapes (cube, icosahedron, octahedron,
tetrahedron, sphere) and the newer orbital station in three (towers, disk, cross) are the docking stations, with the
small trading outpost; the outlaw station is Hyades's, a lawless system. The derelict freighters (six of the game's
layouts, from `POI/HULK/HULKSTRUCTURE01-07`), the starship wreck (`POI/SPACEDEBRIS`), the abandoned station and the
Atlas Interface stand in orbits of their own as structures to fly past (the remake's `nodock`). The Space Anomaly
roams the cluster as a mobile station, docking and all. The game's space portal (`POI/GATE_POI`) is the systems'
jumpgate. Each model is the structure's exterior (a station's interior hangs under a separate subtree, and is left
out), its shape forced through the descriptor, turned so its docking tunnel faces +Z the way the remake launches
ships (the turn is baked into the model, so the glTF importer's X flip can't undo it), coarser detail levels until it
fits its triangle budget, and past LOD floor 1 without the mesh families that have no LODs at all (the interior props,
the derelicts' gore). The big stations are shrunk to the remake's 5 km (the orbital station is 9.5 km across in the
game); the derelicts and the wreck are scaled up x3.5 like the ships, so they keep their size against them. The
stations' materials come over like the ships'. `--classes stations` builds only these; a station model's name
(`--list-classes`) builds that one.

**Ship weapons.** The game's starship weapons are items in the shops (`items.json`): the Photon Cannon, Phase Beam,
Positron Ejector, Infra-Knife Accelerator, Cyclotron Ballista and Rocket Launcher, the Sentinel Cannon of the
interceptors and the living ships' Spewing Vents and Grafted Eyes. Each is based on the original weapon that behaves
most like it (a blaster, an auto-cannon, a scatter gun, a beam laser, an unguided rocket) with the game's own numbers
from its technology table: damage per hit (scaled by 1/150: the game's hulls are in the thousands), the rate of fire
as the reload, the range as the shot's lifetime, the bullets per shot as a salvo or the scatter gun's spread, the
blast radius, a rocket's cooldown; a beam's shield leech becomes extra shield damage. Their names and descriptions
are the game's English texts, their shop icons the game's technology icons on a panel, their bolts the game's own
projectile and bullet textures where those are sprites (the Photon Cannon's and Sentinel Cannon's bullets, the rocket),
their colours the projectiles' lights otherwise, with the game's energy-hit impact and muzzle flash. The remake's
sounds stay (the game's are Wwise banks). `--classes weapons` builds only these; a weapon's id builds that one.

**Sounds.** The ships fly with the game's own engine and boost sounds and the weapons fire with theirs
(ships.json `sounds`, items.json `fx.shot`): the player-ship engine layers per ship type (fighter, hauler, explorer,
shuttle, exotic, sentinel, living ship, racer, Boundary Herald), the drones', the police ship's, the freighters' and
frigates' engine loops, the boost start, loop, end and power-up of each type, each weapon's shots (the Phase Beam's
as a loop) and the rockets' blast, picked from the persistent sound bank by their Wwise paths. The game's sounds are
Wwise Vorbis, which no Python package decodes, so the importer calls `vgmstream-cli` (then `ffmpeg` for Ogg) or
`ww2ogg` from the PATH; without one it says so and builds the mod without sounds (`--no-sounds` skips them on
purpose). On Arch: `yay -S vgmstream-cli-bin`; elsewhere a vgmstream release from its site, on the PATH. The sounds
land in the mod's `audio/` folder, one file per game sound; the remake's own sounds are not replaced.

**Part bonuses.** Each part changes the ship a little by its size against the other parts of its slot, the flavour
No Man's Sky had before its 4.0 update (big wings carried more): wider wings and sails give cargo and cost handling
and turn rate, a bigger cockpit or hull gives hull points and cargo and costs acceleration, bigger engines give speed
and acceleration and cost handling, a few per cent each and 8 at most; small parts give the reverse, accessories
nothing. The Customize screen shows the result as you pick. `--no-part-stats` leaves the parts without them.

**Thrusters.** The engines are reproduced the way the game's own engine code builds them (the decompiled
`cGcSpaceshipEngineEffects` / `cGcStagedJetEngine`): the jet cones the game draws additively under its `STAGE1` and
`STAGE2` nodes, lit by thrust and speed, become the remake's engine flames (main flame cards, posed at the full-thrust end
of their `THRUST` animation, with a flicker noise made from the game's jet texture); its `BOOST` stage jets become boost
cards; the glow discs (`ENGINEGLOW`) glow with the engines; every engine light's colour (the nodes named `ENGINE`) colours
that engine's flames, glow and exhaust effects; the `TRAIL` locators, which carry the game's engine trails, are the
exhaust mounts, sized by their own scale; the `CONTRAIL` locators, the game's wingtip contrails while boosting, are
booster mounts. Each ship's engine colour is its default build's.

**Moving parts.** The parts keep what moves in flight, as the remake plays it (a model's first animation, looped, on
objects that turn or move): the engines' turbines and every other spinner (No Man's Sky's rotation components: the
royal exotic's engine rings, the solar ships' spinning engine parts, the shuttles' and haulers' rotating pods), and the
idle loops some parts have (the fighter wing with the droid on it, the living ships' breathing). Parts that swing out
for flight (the royal exotic's wings folding vertical, the fighters' folding wings, the squid's nose and engines) are
built in their **flying pose**, the end of their take-off animation, and their take-off and landing tracks are kept in
the GLB after the loop, for the day the remake plays a one-shot on launch and landing (`--transitions loop` plays
take-off and landing in a loop instead; `rest` leaves everything as modelled, the landed pose). Landing gear, hatches,
the pilot getting in and out and the thrusters' throttle flaps (control animations) are not exported.
`--no-animations` builds everything static.

## How it reads the game

`nms/` is a small, dependency-free reader of No Man's Sky's files, usable on its own (`research/formats.md` has the
formats):

- `hgpak.py`: HGPAK v2 archives (`NMSARC.*.pak`), the manifest, the chunks, the codec by what the chunk holds
  (Zstandard / LZ4 / Oodle), a folder of archives looked up by name.
- `mbin.py`: MBIN templates with the layouts of libMBIN 7.10 for scenes, descriptors, geometry, materials.
- `descriptors.py`: a procedural model's groups and options, the likeliest choice, the node chooser.
- `scene.py`: a scene tree, its references resolved, every mesh, locator and light placed in one frame.
- `geometry.py`: the vertex streams (half-float positions and UVs, octahedral packed normals) as arrays.
- `textures.py`: DDS (BC1 / BC4 / BC5 / BC7 through Pillow, ASTC through an optional decoder) as PNG.
- `animation.py`: the entity files' animation and rotation components, the `.anim.mbin` keyframes.

- `tables.py`: the technology table (the ship weapons' numbers) and the English texts.
- `audio.py`: the Wwise sound banks' name tables, the streamed and embedded sounds, the outside decoders.

`tools/build.py` turns the classes into the mod; `tools/world.py` the stations and their systems, `tools/weapons.py`
the weapons, `tools/sounds.py` the sounds; `tools/glb.py` writes the GLB parts.

## Tests

```
python3 -m unittest discover -s tests
```

The tests build their own archives and MBIN files; no game files are needed.

## Licence

MIT (see LICENSE). No Man's Sky is © Hello Games; this importer is not affiliated with them.
