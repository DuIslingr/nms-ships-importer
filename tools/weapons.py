"""No Man's Sky's starship weapons as the remake's items (items.json): their numbers from the game's technology
table (damage, rate of fire, range, bullets per shot, blast radius, cooldown), their names and descriptions from
its English texts, their icons from its UI textures and their bolts from the projectiles' own textures.

Each weapon is an item based on the original weapon that behaves most like it (a blaster, an auto-cannon, a scatter
gun, a beam laser, an unguided rocket), so the base's kind, sounds and special behaviour carry over, and the
numbers replace the base's:

- damage: the table's damage per hit x DAMAGE_PER_NMS (No Man's Sky's hulls are in the thousands; the remake's
  shots do 2 to 30), at least 1;
- reload: 1000 / rate of fire (ms); a rocket's its cooldown;
- range: the table's range in metres, as the shot's lifetime at the base's speed (20 units a metre);
- bullets per shot: a scatter gun's spread (its blast), a two-bullet gun's salvo;
- a beam's damage is read per quarter second of beam; its shield leech becomes extra shield damage.
"""
import os
import re

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))

DAMAGE_PER_NMS = 1 / 150.0
UNITS_PER_METRE = 20.0
ICON_SIZE = (180, 88)

# `tech` the technology table id, `base` the original item, `kind` how the numbers map, `fx` the look:
# `bolt` a texture of the game's for the projectile sprite (and its `crop`, a fraction of its width, for sprite sheets),
# `color` the bolt's light, `size` / `stretch` the sprite's size in game units and its length along the flight
WEAPONS = [
    dict(id="photon_cannon", tech="SHIPGUN1", base=12, kind="gun", techLevel=3, price=14000, occurrence=50,
         fx=dict(bolt="textures/effects/lines/shipgun.dds", size=360, stretch=5, glow=2)),
    dict(id="phase_beam", tech="SHIPLAS1", base=9, kind="beam", techLevel=5, price=32000, occurrence=40,
         fx=dict(color=[0.35, 0.95, 1.0], glow=2)),
    # the positron's and infra-knife's bolts are textured capsules (a plain gradient wrapped round a mesh): their colours only
    dict(id="positron_ejector", tech="SHIPSHOTGUN", base=176, kind="scatter", techLevel=6, price=52000, occurrence=35,
         fx=dict(color=[1.0, 0.75, 0.2], glow=3)),
    dict(id="infra_knife", tech="SHIPMINIGUN", base=24, kind="gun", techLevel=7, price=66000, occurrence=35,
         fx=dict(color=[1.0, 0.1, 0.35], glow=3)),
    dict(id="cyclotron_ballista", tech="SHIPPLASMA", base=16, kind="gun", techLevel=8, price=98000, occurrence=30,
         fx=dict(color=[0.29, 0.04, 1.0], size=520, stretch=1, glow=4)),
    dict(id="rocket_launcher", tech="SHIPROCKETS", base=33, kind="rocket", techLevel=5, price=140, occurrence=50,
         fx=dict(bolt="textures/effects/weapons/grenadeplasma.dds", crop=0.25, color=[1.0, 0.55, 0.15], size=600, stretch=2, glow=3)),
    dict(id="sentinel_cannon", tech="SHIPGUN_ROBO", base=26, kind="gun", techLevel=9, price=190000, occurrence=15,
         fx=dict(bolt="textures/effects/lines/shipgunblue.dds", size=360, stretch=5, glow=3)),
    dict(id="spewing_vents", tech="SHIPGUN_ALIEN", base=14, kind="gun", techLevel=9, price=210000, occurrence=12,
         fx=dict(color=[0.55, 1.0, 0.25], size=400, stretch=2, glow=3)),
    dict(id="grafted_eyes", tech="SHIPLAS_ALIEN", base=10, kind="beam", techLevel=9, price=230000, occurrence=12,
         fx=dict(color=[1.0, 0.45, 0.2], glow=3)),
]
# the original bases' projectile speeds (game units per ms, Assets/Resources/GoF2Data/item_attributes.json), the
# range becomes a lifetime at them; a base not listed flies at 20
BASE_SPEED = {12: 14, 9: 20, 176: 22, 24: 22, 16: 17, 33: 16, 26: 28, 14: 17, 10: 20}
IMPACT = "textures/effects/energyhit.dds"
MUZZLE = "textures/common/weapons/multitool/muzzleflash.base.dds"   # a 4 x 4 flipbook: its first frame
MAX_SPRITE = 512


def title(text):
    """"PHOTON CANNON" -> "Photon Cannon" (small words kept small)."""
    small = {"of", "the", "and", "a", "an", "to"}
    words = text.lower().split()
    return " ".join(w if (i and w in small) else "-".join(p.capitalize() for p in w.split("-")) for i, w in enumerate(words))


def stats_for(kind, st):
    """The remake's stats from a technology's stat bonuses."""
    damage = st.get("Guns_Damage", 0.0)
    rate = st.get("Guns_Rate", 1.0) or 1.0
    rng = st.get("Guns_Range", 1000.0)
    bullets = int(st.get("Guns_BulletsPerShot", 1) or 1)
    radius = st.get("Guns_Damage_Radius", 0.0)
    out = {}
    if kind == "beam":
        per_second = st.get("Lasers_Damage", 0.0) * 4          # read as damage per quarter second of beam
        out["damage"] = max(1, round(per_second * 1.2 * DAMAGE_PER_NMS))   # the beam lasers' 1200 ms reload
        out["reloadMs"] = 1200
        out["lifetimeMs"] = 2400
        leech = st.get("ShieldLeech", 0.0)
        if leech:
            out["shieldDamage"] = round(100 + 100 * leech * 5)   # the shields it leeches: extra shield damage
        return out, None
    speed = None
    if kind == "rocket":
        out["damage"] = max(1, round(damage * DAMAGE_PER_NMS))
        out["reloadMs"] = int(1000 * max(st.get("Guns_CoolTime", 1.0), 1.0 / rate))
        out["blastRadius"] = int(radius * UNITS_PER_METRE)
        speed = 16
    elif kind == "scatter":
        out["damage"] = max(1, round(damage * bullets * DAMAGE_PER_NMS))
        out["reloadMs"] = max(100, int(1000 / rate))
        dispersion = st.get("Guns_Dispersion", 5.0)
        out["blastRadius"] = int(rng * np.tan(np.radians(max(dispersion, 1.0))) * UNITS_PER_METRE)   # the spread's width at range
        speed = 22
    else:
        out["damage"] = max(1, round(damage * DAMAGE_PER_NMS))
        out["reloadMs"] = max(90, int(1000 / rate))
        if bullets > 1:
            out["salvoShots"] = bullets
        if radius >= 3:
            out["blastRadius"] = int(radius * UNITS_PER_METRE)
    return out, speed


def icon_image(game_icon):
    """The remake's 180 x 88 shop icon: a dark panel with the game's 256 x 256 icon on its left."""
    im = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.rounded_rectangle([0, 0, ICON_SIZE[0] - 1, ICON_SIZE[1] - 1], radius=10, fill=(16, 20, 26, 255), outline=(96, 116, 136, 255), width=2)
    icon = game_icon.convert("RGBA").resize((72, 72), Image.LANCZOS)
    im.alpha_composite(icon, (10, 8))
    dr.rounded_rectangle([92, 20, 170, 68], radius=6, fill=(28, 34, 42, 255))
    return im


def sprite_image(im, crop=None, frame=None):
    """A projectile sprite from a game texture: RGBA, the first `crop` of its width for a strip of frames, the first
    cell of a `frame` = (columns, rows) flipbook, black as clear, at most MAX_SPRITE wide."""
    im = im.convert("RGBA")
    if crop:
        im = im.crop((0, 0, max(1, int(im.width * crop)), im.height))
    if frame:
        im = im.crop((0, 0, max(1, im.width // frame[0]), max(1, im.height // frame[1])))
    a = np.asarray(im).astype(np.float32)
    if a[..., 3].min() >= 254:   # no alpha: the brightness is the shape (the game draws these additively)
        lum = a[..., :3].max(axis=2)
        a[..., 3] = lum
        im = Image.fromarray(a.astype(np.uint8), "RGBA")
    if max(im.size) > MAX_SPRITE:
        im.thumbnail((MAX_SPRITE, MAX_SPRITE), Image.LANCZOS)
    return im


def build_weapons(banks, out, report, texts, tech, which=None):
    """The weapons' items: their numbers from the technology table, their textures as PNGs. Returns the entries."""
    from nms import tables, textures
    which = {w["id"] for w in WEAPONS} if which is None else set(which)
    items = []
    written = set()

    def png(game_path, rel, make):
        p = game_path.lower()
        dst = os.path.join(out, rel)
        if rel in written:
            return rel
        if not banks.exists(p):
            report.warn(f"{p} is not in the archives")
            return None
        if not os.path.exists(dst):
            try:
                im = make(textures.decode(banks.read(p)))
            except textures.MissingASTC as e:
                report.warn(str(e))
                return None
            except Exception as e:
                report.warn(f"{p}: {e}")
                return None
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            im.save(dst)
        written.add(rel)
        return rel

    for w in WEAPONS:
        if w["id"] not in which:
            continue
        t = tech.get(w["tech"])
        if not t:
            report.warn(f"{w['id']}: {w['tech']} is not in the technology table; skipped")
            continue
        name = title(texts.get(t["name"], w["id"].replace("_", " ")))
        subtitle = texts.get(t["subtitle"], "")
        desc_id = t["name"].replace("_NAME", "_DESCRIPTION")
        description = tables.plain(texts.get(desc_id) or texts.get(t["description"], ""))
        if subtitle:
            description = f"{subtitle}. {description}".strip()
        st = t["stats"]
        stats, speed = stats_for(w["kind"], st)
        if w["kind"] != "beam":
            speed = speed or BASE_SPEED.get(w["base"], 20)
            stats["speed"] = speed
            stats["lifetimeMs"] = int(st.get("Guns_Range", 1000.0) * UNITS_PER_METRE / speed)
        fx = {}
        spec = w["fx"]
        proj = {}
        if spec.get("bolt"):
            rel = png(spec["bolt"], f"fx/{w['id']}_bolt.png", lambda im, c=spec.get("crop"): sprite_image(im, c))
            if rel:
                proj.update({"sprite": rel, "size": spec.get("size", 400), "stretch": spec.get("stretch", 3), "alongFlight": True})
        if spec.get("color"):
            proj["color"] = spec["color"]
        if spec.get("glow"):
            proj["glow"] = spec["glow"]
        if proj:
            fx["projectile"] = proj
        impact = png(IMPACT, "fx/impact.png", sprite_image)
        if impact and w["kind"] != "beam":
            fx["impact"] = {"sprite": impact, "size": 1600 if w["kind"] != "rocket" else 3200, "lifetime": 260, "grow": 2.0}
            if spec.get("color"):
                fx["impact"]["color"] = spec["color"]
        muzzle = png(MUZZLE, "fx/muzzle.png", lambda im: sprite_image(im, frame=(4, 4)))
        if muzzle and w["kind"] in ("gun", "scatter"):
            fx["muzzle"] = {"sprite": muzzle, "size": 420, "lifetime": 80, "grow": 1.3}
            if spec.get("color"):
                fx["muzzle"]["color"] = spec["color"]
        entry = {"id": w["id"], "base": w["base"], "name": {"en": name}, "description": description,
                 "techLevel": w["techLevel"], "occurrence": w["occurrence"], "price": [w["price"], int(w["price"] * 1.12)], "stats": stats}
        if fx:
            entry["fx"] = fx
        icon = png(t["icon"], f"fx/icons/{w['id']}.png", icon_image) if t.get("icon") else None
        if icon:
            entry["icon"] = icon
        items.append(entry)
    return items
