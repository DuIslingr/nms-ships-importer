# No Man's Sky's file formats, as this importer reads them

What was found reading the game's archives directly (NMS 7.10, PC Steam build and the iOS 7.10.4 app, 2026-10-30), with
the layouts of libMBIN 7.10 (monkeyman192/MBINCompiler) for the templates. Nothing from the game is in this repository.

## HGPAK v2 archives (`GAMEDATA/PCBANKS/NMSARC.*.pak`, `GAMEDATA/IOSBANKS/NMSARC.*.pak`)

```
0x00  "HGPAK\0\0\0"
0x08  u64 version = 2
0x10  u64 file count (the manifest counts)
0x18  u64 chunk count
0x20  u8  compressed, 7 bytes pad
0x28  u64 data offset (16-aligned)
0x30  file count x { 16 bytes MD5 of the lower-cased posix path, u64 start offset (absolute), u64 decompressed size }
      chunk count x u64 stored chunk size (compressed archives only)
      the chunks from the data offset, back to back, each padded to 16 bytes
```

Entry 0 is the manifest: the file names separated by CRLF, lower case; name *i* belongs to entry *i* + 1. Decompressed,
the chunks form one stream of C bytes each (the last shorter, and the stream runs past the last file: the real archives
have padding after it); a file at decompressed offset o = start − data offset spans chunks o // C .. ceil((o + size) / C) − 1.
A chunk stored at its full decompressed size is raw (texture banks keep incompressible chunks that way). C and the codec
are the platform's, not in the header:

| Banks | C | Codec | Note |
|---|---|---|---|
| PCBANKS, Windows / Linux | 0x10000 | Zstandard | frames start `28 B5 2F FD` |
| PCBANKS, macOS | 0x20000 | LZ4 block | no magic |
| IOSBANKS (and Switch) | 0x20000 | Oodle Kraken | first byte 0x8C (Mermaid 0xCC, Leviathan 0x8A / 0xCA) |

The reader finds C from the chunk count (the one of 0x10000 / 0x20000 that covers the data in that many chunks) and the
codec from the first compressed chunk's bytes, so a copied folder reads the same on any OS. The PC and the iOS banks of
one version hold the same files (3 437 spacecraft files each, 1 765 of them textures) except the geometry suffix
(`.geometry.mbin.pc` / `.geometry.data.mbin.pc` vs `.mbin.ios`), and the iOS set keeps the materials in
`NMSARC.Materials.pak` where the PC set has `NMSARC.MetadataEtc.pak` (so look files up by name across every archive).

## MBIN

```
0x00  u64 magic: CCCCCCCCCCCCCCCC (MBIN), DDDDDDDDDDDDDDDD (the geometry's .MBIN.PC / .MBIN.IOS)
0x08  u16 MBIN version (3300 in 7.x)      0x0A u16 compiler header version
0x0C  u32 name hash of the root template  0x10 u64 template GUID   0x18 u64 timestamp
0x20  the root template
```

Fields lie at fixed offsets (libMBIN's declaration order, natural alignment). Dynamic fields are 16-byte headers that
point elsewhere in the file, relative to the header's own position: a **list** (i64 offset, i32 count, u32 magic with
low byte 1: `AAAAAA01`, the geometry's `FEFEFE01`), a **string** (`VariableSizeString` / `GcFilename`: i64 offset, i32
length, u32 magic), a **generic list** of mixed templates (the same header; at the offset, count entries of i64 offset
from the entry, u32 name hash, u32 `EEEEEE01`). The PC and the iOS builds of one version write byte-identical MBINs.

Root templates by name hash: `TkSceneNodeData` 0x3DB87E47, `TkModelDescriptorList` 0x4026294F, `TkGeometryData`
0x819C3220, `TkGeometryStreamData` 0x40025754, `TkMaterialData` 0x4737D48A.

| Template | Size | Fields (offset) |
|---|---|---|
| TkSceneNodeData | 0x80 | Attributes list 0x00 (of TkSceneNodeAttributeData 0x20: Name fixed 0x10, Value string 0x10), Children list 0x10, InstanceTransforms 0x20, Name string 0x30, Type fixed 0x10 at 0x40, Transform 0x50 (9 floats: RotX Y Z degrees, ScaleX Y Z, TransX Y Z), NameHash u32 0x74, PlatformExclusion i8 0x78 |
| TkModelDescriptorList | 0x10 | List 0x00 of TkResourceDescriptorList (0x20: Descriptors list 0x00, TypeId fixed 0x10 at 0x10) |
| TkResourceDescriptorData | 0xC8 | Id fixed 0x20 at 0x00, Children generic list 0x20 (TkModelDescriptorList), ReferencePaths list of strings 0x30, Chance f32 0x40, Name fixed 0x80 at 0x44 |
| TkGeometryData | 0x160 | PositionVertexLayout 0x00 and VertexLayout 0x20 (TkVertexLayout 0x20: VertexElements list 0x00 of TkVertexElement 0x0C {Instancing u32, Type i32 (GL enum), Normalise u8, Offset u8, SemanticID u8, Size u8}, ElementCount i32 0x18, Stride i32 0x1C), BoundHull lists 0x40 / 0x50 / 0x60, IndexBuffer 0x70, JointBindings 0x80 (0x68 each: InvBindMatrix 16 f, BindRotate 4 f, BindScale 3 f, BindTranslate 3 f), JointExtents 0x90, JointMirrorAxes 0xA0, JointMirrorPairs 0xB0, MeshAABBMax 0xC0, MeshAABBMin 0xD0, MeshBaseSkinMat 0xE0, MeshVertREnd 0xF0, MeshVertRStart 0x100, ProcGenNodeNames 0x110, ProcGenParentId 0x120, SkinMatrixLayout 0x130, StreamMetaDataArray 0x140 (TkMeshMetaData 0x38: IdString 0x00, Hash u64 0x10, IndexDataOffset / Size 0x18 / 0x1C, VertexDataOffset / Size 0x20 / 0x24, VertexPositionDataOffset / Size 0x28 / 0x2C), CollisionIndexCount 0x150, IndexCount 0x154, Indices16Bit 0x158, VertexCount 0x15C |
| TkGeometryStreamData | 0x10 | StreamDataArray list of TkMeshData (0x48: IdString 0x00, MeshDataStream bytes 0x10, MeshPositionDataStream bytes 0x20, Hash 0x30, IndexDataSize 0x38, VertexDataSize 0x3C, VertexPositionDataSize 0x40) |
| TkMaterialData | 0xA8 | Flags list of u32 0x00, FxFlags 0x10, Link string 0x20, Metamaterial 0x30, Name 0x40, Samplers list 0x50 (TkMaterialSampler 0x50: MaterialAlternativeId fixed 0x20, Map string 0x20, Name string 0x30, Anisotropy, TextureAddressMode, TextureFilterMode, IsCube, IsSRGB, UseCompression, UseMipMaps), Shader string 0x60, Uniforms_Float list 0x70 (0x30: Values 4 f, ExtendedValues list 0x10, Name string 0x20), Uniforms_UInt 0x80, ShaderMillDataHash i64 0x90, TransparencyLayerID i32 0x98, CastShadow 0x9C, Class u8 0x9D (MaterialClassEnum: 2 Additive, 11 Cutout, 12 Decal, 15 DoubleSided, 18 Glow, 19 GlowTranslucent, 45 Opaque, 62 Translucent), CreateFur, DisableZTest, EnableLodFade, UseShaderMill |

Material flags (MaterialFlagEnum, from 0): `_F01_DIFFUSEMAP` 0, `_F03_NORMALMAP` 2, `_F07_UNLIT` 6, `_F16_DIFFUSE2MAP`
15, `_F25_MASKS_MAP` 24, `_F36_DOUBLESIDED` 35, `_F53_COLOURISABLE` 52.

## Scenes

The root is a MODEL node (attributes GEOMETRY = the geometry files without their suffix, NUMLODS, LODDIST1..). Under it:
MESH nodes (BATCHSTARTPHYSI / BATCHSTARTGRAPH, BATCHCOUNT, VERTRSTARTPHYSI / VERTRSTARTGRAPH, VERTRENDPHYSICS /
VERTRENDGRAPHIC, FIRSTSKINMAT, LASTSKINMAT, LODLEVEL, BOUNDHULLST / ED, AABBMIN / MAX, HASH, MATERIAL = the material
file (`.../COCKPITD/HQTRIMPRIMARY_MAT.MATERIAL.MBIN`: one file per material in a folder named after the model), MESHLINK),
LOCATOR, JOINT (JOINTINDEX), LIGHT (FOV, FALLOFF, INTENSITY, RADIUS, COL_R / G / B), COLLISION, REFERENCE (SCENEGRAPH =
another scene put here). Mesh names map to the geometry's stream ids upper-cased (`FrontPadLOD0` -> `FRONTPADLOD0`).

**The transform** (RotX / Y / Z in degrees, scale, translation): the rotations apply **Z first, then X, then Y**
(M = Ry · Rx · Rz), checked against the joint bind poses of 322 rotated joints across the ship parts: the only order of
the six that matches every one of them.

**Procedural models** (`FIGHTER_PROC.SCENE.MBIN` with `FIGHTER_PROC.DESCRIPTOR.MBIN`): the scene holds every option as
a node named like the descriptor's entry (`_Cockpit_D`, a REFERENCE to the part's scene); nested options are children of
their parent option's reference node, in the proc scene (`_Wings_A` -> `_Acc_A`). The descriptor is a tree of groups
(type id = the slot, `_WINGS_`) with options (id `_WINGS_F`, name `_Wings_F` = the node, a chance weight, reference
paths, and the groups that exist only under this option). A part's own scene may have a descriptor of its own
(`WINGS_F.DESCRIPTOR.MBIN`) for its optional details (`_SubWings_E`: locators holding references); both apply. Options
named `_..._NONE` / `_..._NULL` show nothing and have no node.

Classes and their trees (7.10): fighters `_COCKPIT_` 5 / `_ENGINE_` 3 / `_WINGS_` 10 (nested `_ACC_`, `_ANOSE_`);
dropships (haulers) `_COCKPIT_` 9 / `_HULL_` 1 (nested `_ENGINES_` 4, `_WINGS_` 8, deeper `_SUBWINGS_`, `_THRUSTERS_`);
scientific (explorers) `_COCKPIT_` 2 frames (nested `_ACCFRONT_`, `_BACK_`, `_COCKPIT_`, `_WINGS_` ...); shuttle
`_SHUTTLE_` 2 (double / single) -> `_HULL_` -> `_HULL1_` -> ... modular tubes; s-class (exotics) `_SCLASSSHIP_` royal
(nested `_COCKPIT_`, `_ENGINE_`, `_WINGS_`, `_TOPWING_`, `_LANDINGGEAR_`) and squid; sailship (solar) `_BODY_` 6 /
`_SAILS_` 3 / `_TIPS_` 5 / `_WINGS_` 6; sentinelship `_PIT_` 3 / `_SKIRT_` 2 / `_TOPFLAP_` 2 / `_WINGS_` 3 with many
nested groups. Useful locators: `Gun<N>Ref` references (the wings' guns, with `ShipGun` / `EXT_SHOOT` under them),
`RefEngine<N>` references (thrusters, each with `Trail`, `Stage1` / `Stage2` locators), `Contrail<N>`, the engines'
`EngineLight`, `CockpitPos`, `SLOT_*` locators on the proc root.

## Geometry (`.GEOMETRY.MBIN.PC` + `.GEOMETRY.DATA.MBIN.PC`; `.IOS` the same bytes)

Per mesh id, the data file's `MeshDataStream` holds the **vertex stream then the index data** (`IndexDataOffset` =
`VertexDataSize`; `Indices16Bit` says u16 or u32 but some models (the solar ships' proc geometry) say u32 and store
u16, so the width that fits the vertex count wins); `MeshPositionDataStream` holds the position stream. The 7.x
layouts:

- position stream, stride 16: POSITION (semantic 0) half4 (w = 1) at 0, TEXCOORD (semantic 1) half4 (u, v, u2, v2) at 8;
- vertex stream, stride 8: COLOUR (semantic 4) ubyte4 at 0, and at 4 a packed u32 (semantic 11, type GL_UNSIGNED_INT,
  size 1) with the **normal as an octahedral pair of 10-bit unsigned fields in bits 0-9 and 10-19** (0.98-0.99 mean
  agreement with the face normals of several meshes; every other reading tried, 2_10_10_10, 8-bit octahedral, quaternion
  tangent frames, scored under 0.6); bits 20-31 are the tangent (not decoded).
- skinned parts (the solar ships): stride 20, BLENDINDICES ubyte4 (semantic 5) at 4, BLENDWEIGHTS half4 (semantic 6)
  at 8, the packed u32 at 16.

GL type enums: 5120 byte, 5121 unsigned byte, 5122 short, 5123 unsigned short, 5125 unsigned int, 5126 float, 5131 half.
Units are metres, +Y up, the nose along +Z (a fighter is about 9 m wide, 7.5 m long, 4.4 m tall).

## Textures

DDS, mipmapped, 2048² down to 256². PC: DXT1 (BC1, the base maps), ATI2 (BC5, normal maps: two channels, the blue
rebuilt), DX10 BC7 (DXGI 98) and ATI1 (BC4) for single-channel masks; Pillow decodes all four. iOS: ASTC in DX10 headers
(DXGI 134 = 4x4, 142 = 6x6, 150 = 8x8, 162 = 10x10), 256², which Pillow doesn't decode: `astc_decomp_faster` or
`astcenc`. Material samplers: `gDiffuseMap` (`<name>.BASE.DDS`), `gMasksMap` (`.MASKS.DDS`: R ambient occlusion, G
roughness, B metallic), `gNormalMap` (`.NORMAL.DDS`). Paint: materials named `*primary*`, `*secondary*`, `*tertiary*`
(the shared `FIGHTERS/SHARED/PRIMARY.DDS` and the like) take the ship's palette; `gMaterialColourVec4` tints.

## Animations

A model's entity file (`<folder>/<model>/entities/<name>.entity.mbin`, named by the `ATTACHMENT` attribute of one of its
nodes, usually a LOCATOR `Data`) is a `TkAttachmentData` (name hash 0x6874FF60): AdditionalData list 0x00, Components
list 0x10 of 0x20-byte `LinkableNMSTemplate` entries, each a template reference (i64 offset from the entry, u32 name
hash, u32 `EEEEEE01`) plus a string. The components the ships use:

- `TkAnimationComponentData` (0x573A9AA9, 0x1A0): `Idle` TkAnimationData inline at 0x00, `AnimGroup` 0x128, AnimLibraries
  0x138, `Anims` list 0x148 of TkAnimationData (0x128 each: `Anim` fixed 0x10 at 0x50, `Filename` string 0x70, `AnimType`
  u32 0xB8 (0 Loop, 1 OneShot, 2 OneShotBlendable, 3 Control), FrameEnd 0xC4, FrameEndGame 0xC8, FrameStart 0xCC,
  Priority 0xD8, Speed f32 0xDC, StartNode fixed 0x40 at 0xE0, Active 0x120, Additive 0x121). The spacecraft use: `""`
  / `IDLE` / `FLYINGIDLE` / `COCKPITIDLE` loops (few parts), `TAKEOFF` / `LANDING` one-shots (wings, engines, noses that
  change shape for flight), `GEARUP` / `GEARDOWN` (landing gear), `ENTER` / `EXIT` / `EJECT` (the pilot), `THRUST`
  (Control: the thruster flaps follow the throttle).
- `TkRotationComponentData` (0x8EB35CA7): `Axis` Vector3f 0x00 (padded to 16), `Speed` f32 0x10 (turns per second as
  this importer reads it: 0.1 the usual spinner, 0.5 the fighters' engine turbines, 2.0 effects; negative reverses),
  `SyncGroup` i32 0x14, `AlwaysUpdate` 0x18, `UseModelNode` 0x19. The node carrying the attachment (a MESH or a
  LOCATOR with meshes under it) turns about the axis in its own frame, forever.

`.ANIM.MBIN` is a `TkAnimMetadata` (0x8E7F1986): `StillFrameData` TkAnimNodeFrameData inline at 0x00 (0x30: Rotations
list 0x00, Scales list 0x10, Translations list 0x20), `AnimFrameData` list 0x30 of TkAnimNodeFrameData, one per frame,
`NodeData` list 0x40 of TkAnimNodeData (0x20: Node string 0x00, RotIndex 0x10, ScaleIndex 0x14, TransIndex 0x18),
FrameCount 0x50, NodeCount 0x54, Has30HzFrames 0x58. Rotations are packed 3 x u16 per quaternion (the list header's
count is the number of u16): `scale = 1 / (0x3FFF sqrt 2)`, `qx = scale ((cx & 0x7FFF) - 0x3FFF)`, `qy` the same from
`cy`, `qz = scale (cz - 0x3FFF)`, the fourth `sqrt(1 - ...)`, and the dropped component is `(cy >> 15) | ((cx >> 14) & 2)`:
3 x, 2 y, 1 z, 0 w. Scales and translations are Vector3f (16 bytes). A node's index below the frame lists' length picks
the animated value; at or past it, the still frame's value at index minus that length. 30 frames per second.

## Engine effects (from the iOS 7.10.4 decompilation)

`cGcSpaceshipComponent::UpdateEngineEffects` fills a Settings block each frame (thrust power, a speed value, boost,
the pulse-drive factor, an engine on/off ramp) and `cGcSpaceshipEngineEffects::Update` drives:

- `cGcStagedJetEngine` (prepared by walking the engine's nodes): nodes whose upper-cased name holds `STAGE1` go to jet
  stage 0, `STAGE2` to stage 1, `BOOST` to stage 2 (`AddJetStage` clones each stage node's material, `JetMatClone_%d_%d`,
  so its `gMaterialColourVec4` can be set per stage); lights whose name holds `ENGINE` are the engine lights. Per frame:
  `UpdatePower(power)` activates every stage node when power > 0; `UpdateStage(alpha, stage)` sets each stage's material
  colour to (1, 1, 1, alpha) with alpha = power for stage 0, max(speed, boost) blended toward 1 by the pulse-drive factor
  for stage 1, and boost for stage 2 (each `x + k (1 - x)` with k = 0 from `GcSpaceshipGlobals` at 0x1A50-0x1A58);
  `UpdateLight(power * (0.5 + 0.5 speed))` scales the engine lights' intensity (0.5 from `GcSpaceshipGlobals` 0x14C0).
- The six control animations of the engine's animation components (`AnimLookup<6>`, among them `THRUST`) are set to a
  time from the settings each frame (thrust, its negative, the pulse factor, the ramp): the `THRUST` animation grows the
  `J_Scale` / `Stage` nodes from 0.3 / 0.18 (idle) to 0.5 (full thrust), so a jet's size follows the throttle.
- `RecreateTrails`: locators named `TRAIL...` are the engine trails, `CONTRAIL...` the contrails (`...SAIL...` the solar
  ships' sail trails); `ENGINEGLOW` and `ENGINEMESHVFXREF` nodes are found by name as well; `EngineEffectMeshLocator_%i`
  nodes are added for the effect meshes.
- `TkRotationComponentData` spinners and `cGcCustomisationThrusterEffects` (the player's chosen thruster effect) sit
  beside this.

The jet texture `TEXTURES/EFFECTS/SHIP/ENGINE_JET.DDS` is a streaked gradient along u (bright at the nozzle), the glow
discs `TEXTURES/COMMON/SPACECRAFT/SHARED/ENGINEGLOW.*.DDS` soft discs. A fighter's jet cone is about 0.6 m long at full
thrust (its mesh is scaled 0.24 under Stage2 0.5 under J_Scale 0.5); the long streaks seen in flight are the trails.

## Tables (`METADATA/REALITY/TABLES/*.MBIN`, `LANGUAGE/*.MBIN`)

The reality tables are MBINs like the rest: fixed-offset structures, 16-byte list and string headers (i64 offset
from the header, i32 count, u32 magic `0xAAAAAA01`). Two are read:

- **The technology table** (`NMS_REALITY_GCTECHNOLOGYTABLE.MBIN`, 393 entries in 7.10): the list header at 0x20,
  entries of 736 bytes. The ID string (0x10) sits **264 bytes into the entry**; before it, at ID-0x58, the icon
  path's string header and at ID-0x10 the description text id's; after it the name text id at ID+0xBC (0x40), the
  subtitle's string header at ID+0x60, the requirements list at ID+0x30 (0x18 each: item id 0x10, i32 amount) and
  the stat bonuses list at ID+0x50 (12 bytes each: f32 value, i32 level, u32 stat type). The stat types are the
  game's `GcStatsTypes` enum. The binary's strings hold the enum's names in order, but a name that also occurs
  elsewhere (`Ship_Weapons_Guns`, `Ship_Weapons_Lasers`, `Ship_Weapons_Missiles`) is stored once and so is missing
  from the run; the numbering here is fixed from the Photon Cannon's own entry (`SHIPGUN1`): 120 Guns_Damage (320),
  121 Guns_Rate (7.5), 122 Guns_HeatTime, 123 Guns_CoolTime, 124 Guns_Scale, 125 Guns_BulletsPerShot,
  126 Guns_Dispersion, 127 Guns_Range (1500), 128 Guns_Damage_Radius, then 129 Lasers (the flag), 130 Lasers_Damage
  (the Phase Beam's 250), 131 Lasers_HeatTime (2.5), 141 ShieldLeech (0.2). The ship weapons: `SHIPGUN1` Photon
  Cannon, `SHIPLAS1` Phase Beam, `SHIPSHOTGUN` Positron Ejector (14 bullets, 10 degrees, 500 m), `SHIPMINIGUN`
  Infra-Knife, `SHIPPLASMA` Cyclotron Ballista (2 bullets), `SHIPROCKETS` Rocket Launcher (6500 damage, 5000 m,
  10 s cooldown, 15 m radius), `SHIPGUN_ROBO` Sentinel Cannon, `SHIPGUN_ALIEN` / `SHIPLAS_ALIEN` the living ships'.
- **The language files** (`NMS_LOC1_ENGLISH.MBIN` ... `NMS_UPDATE3_ENGLISH.MBIN`, 85k texts together): the list
  header at 0x20, entries of 304 bytes: a 0x20 id, then one 16-byte string header per language; the first non-empty
  is the text. Texts carry markup (`<TECHNOLOGY>...<>`, `<IMG>SHIPFIRE<>` for a control's glyph).

## Space structures

The stations are built like the ships: `SPACESTATION.SCENE.MBIN` with a descriptor whose one group `_STATION_` picks
the shape (`_Station_Cub` / `_Ico` / `_Oct` / `_Tet` / `_Sphere`, the pirate and abandoned stations' files the same
without the Tet); under each shape's node a `Station_<shape>` subtree (the interior: the launch tube, the hall, the
shops, 2.6 M triangles) and an `Outside_<shape>` subtree (the hull: 60-140 k triangles), the sphere's hull in a
referenced scene (`MODULARPARTS/EXTERIOR/STATION_SPHERE`: `Entrance1` the interior, `_Outside_Sphere` the hull). The
docking tunnel's locators are named `TunnelOpening`. The newer type B station's exterior is its own scene
(`SPACESTATIONTYPEB_EXTERIOR`, groups `_TYPE_`: Tet / Oct / Disk / EX / Tri / Simple, with `_TunnelOpeningREF_`),
9.5 km across with its `ExtBuildRing`, the base-building limit ring of light. The Anomaly (`ANOMALY/ANOMALY`, 390 m)
holds its rooms in the same scene as its shell (`Exterior`, `OuterRing`); its `Approach` locator is at +Z. The derelict
freighters are `POI/HULK/HULKSTRUCTURE01-07` (75-340 m, each a layout of habitat modules, gantries and a core from
`HULK/PARTS`; `HULK.SCENE` picks among them); an open habitat's interior gore (`_Jar`, `Bones`, `Flesh`, `PortalBlood`)
has no LODs while the hulls have four. The outpost (`POI/OUTPOST`, 250 m, `MainEntrance` at -Z) and the wreck
(`POI/SPACEDEBRIS`, a ship's parts strewn among asteroids) likewise. The space portal is `POI/GATE_POI` (1.1 km, the
ring in the XY plane). The sentinel drones (`COMMON/ROBOTS/DRONE*`, 2-3 m) look along -Z: their eye and guns lie there
and their engine behind; their scenes carry one eye and engine-effect mesh per state (`PatrolEye`, `AttackEye`,
`InvestEye`) and a `critmesh` for critical hits.

## Sounds (`AUDIO/WINDOWS/*.BNK`, `*.TXT`, `MEDIA/*.WEM`)

Wwise. The persistent bank `NMS_AUDIO_PERSISTENT.BNK` holds the game's sound objects and 4 911 small in-memory
sounds (its `DIDX` chunk: u32 id, u32 offset, u32 size per entry, into the `DATA` chunk); the 21 008 streamed sounds
are `MEDIA/<id>.WEM`. Beside each bank the game ships Wwise's SoundbanksInfo listing as `<bank>.TXT`: tab-separated
blocks (`Event`, `Switch`, `State`, `Game Parameter`, `Streamed Audio`, `In Memory Audio` ...), the audio rows giving
id, name, source file, generated `<id>.wem` and the Wwise Object Path, the project's folder tree, which names a
sound's use: `\Actor-Mixer Hierarchy\Player\Ship\Pl_Ship\Pl_Ship_Engines\Pl_Ship_Engines_Fighter\Pl_Ship_Space\
Pl_Ship_Fighter_Space_Speed2_Rr` (the fighter's rear engine layer at speed 2), `...\Pl_Ship_Weapons\Wpn_Ship_Positron_
Fire\...`, `...\NPCs\NPC_Ships\NPC_Ship_Engines\NPC_Ship_Engine_Drone\Drone_Engine_Rear_01`. The other banks are
the loading music (`MUS_LOADING01-52`), the localized voice banks and the Pulse instrument maps. The event-to-sound
links are in the bank's `HIRC` objects and are not needed: the paths say enough.

The WEMs are RIFF with fmt tag 0xFFFF, Wwise Vorbis (a 0x42-byte fmt with the setup data, no `vorb` chunk): Ogg
Vorbis with the page and header structure stripped and the codebooks taken from Audiokinetic's packed set, so neither
ffmpeg nor Python's libraries read them; vgmstream and ww2ogg (with `packed_codebooks_aoTuV_603.bin`) do.

## Tools that read these formats

monkeyman192/HGPAKTool (the archive spec), monkeyman192/MBINCompiler (libMBIN, the template layouts; v7.10.0.1 for 7.10),
NMSDK (Blender). Checked here: the PC and the iOS archives of NMS 7.10 decompress and decode with the same code, the
iOS banks through pyooz 0.0.8 (`import ooz; ooz.decompress(chunk, 0x20000)`).
