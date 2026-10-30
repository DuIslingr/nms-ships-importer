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

(`py import.py ...` on Windows.) The game folder is the one holding `GAMEDATA` (Steam: `.../steamapps/common/No Man's Sky`);
the `PCBANKS` or `IOSBANKS` folder itself works too. The mod is written to `nms_ships` next to `import.py` (`--out` for
elsewhere; `--zip` also zips it). A build of every class takes a minute or two.

| Option | |
|---|---|
| `--classes fighter,hauler` | Only these classes (`--list-classes` shows them: fighter, hauler, explorer, shuttle, exotic, solar, sentinel). Default: all. |
| `--max-parts N` | Parts per slot at most (default 14): the fighters have ten wings, the shuttles dozens of hull pieces. |
| `--max-variants N` | Variants of one part over its nested accessories (default 4): `Wings F`, `Wings F (Acc A3)` ... |
| `--max-texture N` | The textures' longest side (default 2048; 1024 for phones). |
| `--limit-parts N` | A quick test build with N parts per slot. |
| `--fresh` | Delete the output folder first. |
| `--config file` | Settings as JSON; `config.json` next to `import.py` is read by itself (copy `config.example.json`). |

Put the built `nms_ships` folder (or its zip) in the remake's mods folder (the game's Settings > Mods page says where)
and turn it on. The ships are sold by the ordinary ship dealers now and then (from tech level 3) and in the Space
Lounges; in the hangar, **Customize ship** under Inspect ship opens the parts and colours.

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

Each kit's ship (ships.json) has the class's look in stats: fighters fast and lightly loaded, haulers slow with a big
hold, exotics the best handling. Their guns sit where No Man's Sky puts them (the wings' gun references), their exhausts
at the thrusters, with the engine light's colour. Five colour slots (primary, secondary and tertiary paint: No Man's
Sky's own paint materials; lights; engines) with a palette of fourteen paints and seven light colours, and five preset
schemes. The parts keep No Man's Sky's materials: base colour, the masks map as metallic / smoothness, the normal map,
glows as emission. Landing gear and pads, engine jets (the remake draws its own flames) and decals are left out.

Every part is the whole of its option: a wing with the accessory and nose that No Man's Sky's likeliest choice gives
it, as one piece; the other choices are further parts of the slot (up to `--max-variants`). A class is one ship type,
so every part of a kit fits every build of it. No Man's Sky's one ship gun model stays on the hull at the game's gun
points, as the base game's ships carry theirs; the weapon mounts sit at the same points, so your shots leave its barrels,
missiles too (No Man's Sky has no second weapon class: its rockets fire from the same two gun points).

**Part bonuses.** Each part changes the ship a little by its size against the other parts of its slot, the flavour
No Man's Sky had before its 4.0 update (big wings carried more): wider wings and sails give cargo and cost handling
and turn rate, a bigger cockpit or hull gives hull points and cargo and costs acceleration, bigger engines give speed
and acceleration and cost handling, a few per cent each and 8 at most; small parts give the reverse, accessories
nothing. The Customize screen shows the result as you pick. `--no-part-stats` leaves the parts without them.

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

`tools/build.py` turns the classes into the mod; `tools/glb.py` writes the GLB parts.

## Tests

```
python3 -m unittest discover -s tests
```

The tests build their own archives and MBIN files; no game files are needed.

## Licence

MIT (see LICENSE). No Man's Sky is © Hello Games; this importer is not affiliated with them.
