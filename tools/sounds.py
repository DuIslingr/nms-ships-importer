"""No Man's Sky's sounds on the mod's ships and weapons: each ship's engine loop and boost sounds (the remake's
ships.json `sounds`), each weapon's shot (and a rocket's blast) from the game's persistent sound bank, picked by
their Wwise paths and names (`nms/audio.py`). The sounds are decoded through an outside tool (vgmstream-cli or
ww2ogg) into the mod's `audio/` folder, one file per game sound; without one the mod is built without sounds.

The game's player-ship sounds come per ship type (Fighter, Dropship, Scientific, Shuttle, Royal, Alien, Robot, Racer,
SpookShip, Pirate) as speed layers (`..._Space_Speed1..4`, front and rear): the rear mid-speed layer is the remake's
one engine loop, the boost start / loop / end / power-up one-shots its boost sounds. The NPC craft have engine loops
of their own (drones, the police ship, the freighters and frigates).
"""
import os
import re

# a voice: the engine loop and the boost sounds, as (path pattern, name pattern) pairs, the first matches taken
VOICES = {
    "fighter": dict(engine=(r"Pl_Ship_Engines_Fighter", r"^Pl_Ship_Fighter_Space_Speed2_Rr$"), boost="generic"),
    "hauler": dict(engine=(r"Pl_Ship_Engines_Dropship\\", r"^Pl_Ship_Engine_Space_Speed2_Rear$"), boost="generic"),
    "explorer": dict(engine=(r"Pl_Ship_Engines_Scientific", r"^Pl_Ship_ScientificSpace_Speed2_Rr$"), boost="generic"),
    "shuttle": dict(engine=(r"Pl_Ship_Engines_Shuttle", r"^Pl_Ship_Shuttle_Space_Speed2_Rr$"), boost="generic"),
    "exotic": dict(engine=(r"Pl_Ship_Engines_Royal", r"^Pl_Ship_ScientificSpace_Speed1_Rr$"), boost="generic"),
    "sentinel": dict(engine=(r"Pl_Ship_Engines_Robot", r"^Pl_Ship_Robot_Internal_Space_Medium$"), boost="robot"),
    "living": dict(engine=(r"Pl_Ship_Engines_Alien", r"^Ship_Bioship_Speed_Internal_Space_Med$"), boost="alien"),
    "racer": dict(engine=(r"Pl_Ship_Engines_Racer", r"^Ship_Racer_Speed_External_Atmos_Med$"), boost="racer"),
    "spookship": dict(engine=(r"Pl_Ship_Engines_SpookShip", r"^Pl_Ship_SpookShip_Speed_External_Space_Med$"), boost="spookship"),
    "pirate": dict(engine=(r"Pl_Ship_Engines_Pirate", r"^Ship_Pirate_Speed_Internal_Space_Med$"), boost="pirate"),
    "drone": dict(engine=(r"NPC_Ship_Engine_Drone\\", r"^Drone_Engine_Rear_01$")),
    "corrupted_drone": dict(engine=(r"NPC_Ship_Engine_Corrupted_Drone", r"^Corrupted_Drone_Engine_Mid_01$")),
    "freighter_drone": dict(engine=(r"Freighter_Drone_Engine", r"^Freighter_Drone_Engine$")),
    "swarm": dict(engine=(r"NPC_Ship_SwarmDrone\\", r"^SwarmDrone_Engine_01$")),
    "police": dict(engine=(r"\\Police\\", r"^Police_Ship_Loop_01$")),
    "freighter": dict(engine=(r"NPC_Ship_Engine_Freighter", r"^Freighter_Engine_Rear_01$")),
    "frigate": dict(engine=(r"NPC_Ship_Engine_Frigate", r"^NPC_Ship_Engine_Frigate_01$")),
    "living_frigate": dict(engine=(r"\\Frigate_Living\\", r"^Frigate_Living_01$")),
}
BOOSTS = {
    "generic": dict(start=(r"Ship_Boost_Start_Type\\Pl_Ship_Boost_Start\\", r"^Pl_ShiP_Boost_Start_0[1-4]$"), loop=(r"Pl_Ship_Boost_Location\\Pl_Ship_Boost_Lp_Space", r"^Pl_Ship_Boost_Lp_Rr$"),
                    stop=(r"Ship_Boost_End_Type\\Pl_Ship_Boost_End\\", r"^Pl_Ship_Boost_End_0[1-4]$"), charger=(r"Ship_Boost_PowerUp_Type\\Pl_Ship_Boost_PowerUp\\", r"^Pl_Ship_Boost_PowerUp_01$")),
    "robot": dict(start=(r"Pl_Ship_Boost_Start_Robot", r"_0[1-4]$"), loop=(r"Pl_Ship_Robot_Location\\Pl_Ship_Boost_Lp_Space", r"_Rr$"), stop=(r"Pl_Ship_Boost_End_Robot", r"_0[1-4]$")),
    "alien": dict(start=(r"Pl_Ship_Boost_Start_Alien", r"_0[1-4]$"), loop=(r"\\Pl_Ship_Boost\\Boost_Ship_Type\\", r"^Ship_Bioship_Internal_Boost$"), stop=(r"Pl_Ship_Boost_End_Alien", r"_0[1-4]$"),
                  charger=(r"Pl_Ship_Boost_PowerUp_Alien", r"_01$")),
    "racer": dict(start=(r"Pl_Ship_Boost_Start_Racer", r"_0[1-4]$"), loop=(r"Pl_Ship_Racer_Location\\Pl_Ship_Boost_Lp_Space", r"^Ship_Racer_Boost_Space_Fr$"), stop=(r"Pl_Ship_Boost_End_Racer", r"_0[1-4]$"),
                  charger=(r"Pl_Ship_Boost_PowerUp_Racer", r"_01$")),
    "spookship": dict(start=(r"Pl_Ship_Boost_Start_SpookShip", r"_0[1-4]$"), loop=(r"Pl_Ship_SpookShip_Location\\Pl_Ship_Boost_Lp_Space", r"Space_External$"), stop=(r"Pl_Ship_Boost_End_SpookShip", r"_0[1-4]$"),
                      charger=(r"Pl_Ship_Boost_PowerUp_SpookShip", r"_01$")),
    "pirate": dict(start=(r"Ship_Boost_Start_Type\\Pl_Ship_Boost_Start\\", r"^Pl_ShiP_Boost_Start_0[1-4]$"), loop=(r"Pl_Ship_Pirate_Location\\Pl_Ship_Boost_Lp_Space", r"^Ship_Pirate_Boost_Space_Lp_Fr$"),
                   stop=(r"Ship_Boost_End_Type\\Pl_Ship_Boost_End\\", r"^Pl_Ship_Boost_End_0[1-4]$")),
}
# which voice a ship has: by its class / capital id, else by the kit's class prefix
SHIP_VOICES = {
    "fighter": "fighter", "hauler": "hauler", "explorer": "explorer", "shuttle": "shuttle", "exotic": "exotic", "solar": "explorer",
    "sentinel": "sentinel", "living": "living", "golden_vector": "fighter", "rasamama": "fighter", "utopia_speeder": "fighter",
    "horizon_vector": "fighter", "starborn_runner": "sentinel", "racer": "racer", "racer_se": "racer", "boundary_herald": "spookship",
    "bio_fighter": "living", "police_ship": "police", "drone_ship": "drone", "swarm_fighter": "swarm", "swarm_drone": "swarm",
    "sentinel_drone": "drone", "armoured_drone": "drone", "summoner_drone": "drone", "medic_drone": "drone", "corrupted_drone": "corrupted_drone",
    "cargo_scan_drone": "freighter_drone", "freighter_drone": "freighter_drone",
    "living_frigate": "living_frigate", "combat_frigate": "frigate", "science_frigate": "frigate", "diplomatic_frigate": "frigate",
    "industrial_frigate": "frigate", "support_frigate": "frigate", "normandy": "frigate", "ghost_frigate": "frigate",
    "swarm_frigate": "swarm", "swarm_hive": "swarm", "sentinel_capital": "freighter",
}
CAPITAL_VOICE = "freighter"
# the weapons' shots: (path pattern, name pattern, how many files at most), a beam's as a loop, a rocket's blast
WEAPON_SOUNDS = {
    "photon_cannon": dict(shot=(r"Wpn_Ship_Laser_Class_01_Layer_01", r"^Pl_Ship_Laser01_0[1-4]$")),
    "phase_beam": dict(shot=(r"\\Wpn_Ship_Laser\\Wpn_Ship_Laser_01", r"^Wpn_Ship_Laser01_01$"), loops=True),
    "positron_ejector": dict(shot=(r"Wpn_Ship_Positron_Fire", r"_0[1-4]$")),
    "infra_knife": dict(shot=(r"Wpn_Ship_Infraknife_Fire", r"_0[1-4]$")),
    "cyclotron_ballista": dict(shot=(r"Wpn_Ship_Cyclotron_Fire", r"_0[1-4]$")),
    "rocket_launcher": dict(shot=(r"Wpn_Ship_Missile\\", r"^Pl_Ship_Missile_Shoot_0[1-3]$"), blast=(r"Expl_Ships_Med", r"^Expl_Med01_0[1-3]$")),
    "sentinel_cannon": dict(shot=(r"\\Robots\\Drones\\Drone_Laser", r"^Drone_Laser_0[2-5]$")),
    "spewing_vents": dict(shot=(r"Wpn_Ship_Laser_Class_01_Layer_02", r"_0[1-4]$")),
    "grafted_eyes": dict(shot=(r"\\Wpn_Ship_Laser\\Wpn_Ship_Laser_01", r"^Wpn_Ship_Laser01_02$"), loops=True),
}
AUDIO_DIR = "audio"


class Converter:
    """Converts the bank's sounds into the mod once each, by name: `files(sounds)` -> the mod-relative paths."""

    def __init__(self, bank, decoder, out, report):
        self.bank, self.decoder, self.out, self.report = bank, decoder, out, report
        self.done = {}
        self.failed = 0

    def file(self, sound):
        if sound.name in self.done:
            return self.done[sound.name]
        rel = None
        wem = self.bank.wem(sound)
        if wem is None:
            self.report.warn(f"sound {sound.name}: its file is not in the archives")
        else:
            base = os.path.join(self.out, AUDIO_DIR, re.sub(r"[^A-Za-z0-9_.-]+", "_", sound.name))
            os.makedirs(os.path.dirname(base), exist_ok=True)
            try:
                existing = next((base + ext for ext in (".ogg", ".wav") if os.path.exists(base + ext)), None)
                path = existing or self.decoder.convert(wem, base)
                rel = os.path.relpath(path, self.out).replace(os.sep, "/")
            except Exception as e:
                if self.failed == 0:
                    self.report.warn(f"sound {sound.name}: {e}")
                self.failed += 1
        self.done[sound.name] = rel
        return rel

    def files(self, sounds, limit=4):
        """The mod files of the first `limit` distinct sounds, by name."""
        seen, out = set(), []
        for s in sorted(sounds, key=lambda x: x.name):
            if s.name in seen:
                continue
            seen.add(s.name)
            f = self.file(s)
            if f:
                out.append(f)
            if len(out) >= limit:
                break
        return out


def pick(bank, spec):
    path, name = spec
    return bank.find(path, name)


def voice_of(ship):
    """The voice for a ships.json entry (a kit ship by its kit's class, a capital ship by its id)."""
    sid = ship["id"]
    if sid in SHIP_VOICES:
        return SHIP_VOICES[sid]
    base = sid.split("-")[0]
    if base in SHIP_VOICES:
        return SHIP_VOICES[base]
    if base.split("_")[0] in SHIP_VOICES:
        return SHIP_VOICES[base.split("_")[0]]
    return CAPITAL_VOICE if "kit" not in ship else None


def ship_sounds(bank, conv, voice):
    """The remake's `sounds` block for a voice, or None."""
    v = VOICES.get(voice)
    if not v:
        return None
    out = {}
    engine = conv.files(pick(bank, v["engine"]), 1)
    if engine:
        out["engine"] = {"file": engine[0], "volume": [0.15, 0.27], "pitch": [0.9, 1.1]}
    b = BOOSTS.get(v.get("boost"))
    if b:
        start = conv.files(pick(bank, b["start"]), 4)
        if start:
            out["boostStart"] = {"files": start, "volume": 0.4, "pitch": [0.95, 1.05]}
        loop = conv.files(pick(bank, b["loop"]), 1)
        if loop:
            out["boostLoop"] = {"file": loop[0], "volume": [0.5, 1.0], "pitch": [1.0, 1.3]}
        stop = conv.files(pick(bank, b["stop"]), 4)
        if stop:
            out["boostStop"] = {"files": stop, "volume": 0.25}
        if "charger" in b:
            charger = conv.files(pick(bank, b["charger"]), 1)
            if charger:
                out["charger"] = {"file": charger[0], "volume": [0.1, 0.5], "pitch": [0.7, 1.4]}
    return out or None


def apply(banks, out, report, ships, items, decoder=None, bank=None):
    """Gives the ships their engine and boost sounds and the weapons their shots. Returns how many sound files the mod
    got, or -1 when no decoder is there (nothing is changed then)."""
    from nms import audio
    bank = bank or audio.SoundBank(banks)
    if not bank.sounds:
        report.note("no sound bank table (audio/windows/nms_audio_persistent.txt): no sounds")
        return 0
    decoder = decoder or audio.Decoder()
    if not decoder.available:
        report.warn("no WEM decoder on the PATH (vgmstream-cli, or ww2ogg): the mod is built without the game's sounds. "
                    "Arch: yay -S vgmstream-cli-bin; then build again")
        return -1
    conv = Converter(bank, decoder, out, report)
    per_voice = {}
    for ship in ships:
        voice = voice_of(ship)
        if not voice:
            continue
        if voice not in per_voice:
            per_voice[voice] = ship_sounds(bank, conv, voice)
        if per_voice[voice]:
            ship["sounds"] = per_voice[voice]
    for item in items:
        spec = WEAPON_SOUNDS.get(item["id"])
        if not spec:
            continue
        shot = conv.files(pick(bank, spec["shot"]), 4)
        fx = {}
        if shot:
            fx["shot"] = shot if len(shot) > 1 else shot[0]
            fx["shotLoops"] = bool(spec.get("loops"))
        if spec.get("blast"):
            blast = conv.files(pick(bank, spec["blast"]), 3)
            if blast:
                fx["explosionSound"] = blast if len(blast) > 1 else blast[0]
        if fx:
            item.setdefault("fx", {}).update(fx)
    return len([f for f in conv.done.values() if f])
