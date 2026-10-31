#!/usr/bin/env python3
"""Builds the nms_ships mod for the Galaxy on Fire 2 Unity Remake from your own copy of No Man's Sky.

    python3 import.py <game folder or PCBANKS / IOSBANKS folder> [--out nms_ships] [--classes fighter,hauler]

The game folder is the Steam / GOG install (Windows, Linux, macOS: its GAMEDATA/PCBANKS) or the iOS app's GAMEDATA
(IOSBANKS). Nothing from the game is in this repository: the mod is built on your device from your own files.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

CONFIG = os.path.join(HERE, "config.json")


def fail(msg):
    print("Error: " + msg, file=sys.stderr)
    sys.exit(1)


def check_python():
    if sys.version_info < (3, 9):
        fail("Python 3.9 or newer is needed")
    missing = []
    for mod, pkg in (("numpy", "numpy"), ("PIL", "pillow")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        fail("install " + " and ".join(missing) + ": python3 -m pip install " + " ".join(missing))


def load_config(path, ap):
    """config.json (or --config): {"option": value} named as on the command line without the dashes; the command line wins."""
    if not os.path.exists(path):
        return {}
    try:
        cfg = json.load(open(path, encoding="utf-8-sig"))
    except ValueError as e:
        fail(f"{path} isn't valid JSON: {e}")
    if not isinstance(cfg, dict):
        fail(f'{path} must be a JSON object: {{"option": value, ...}}')
    known = {a.dest for a in ap._actions} - {"help", "config", "list_classes"}
    out = {}
    for k, v in cfg.items():
        if k.startswith("_"):
            continue
        dest = k.lstrip("-").replace("-", "_")
        if dest not in known:
            fail(f'{path}: unknown option "{k}" (known: {", ".join(sorted(known))})')
        if dest == "classes" and isinstance(v, list):
            v = ",".join(v)
        out[dest] = v
    return out


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Builds the nms_ships mod for the Galaxy on Fire 2 Unity Remake from your own No Man's Sky files.")
    ap.add_argument("game", nargs="?", help="the game folder, or its GAMEDATA/PCBANKS or GAMEDATA/IOSBANKS folder")
    ap.add_argument("--classes", default="all", help="what to build: all (default), or a list like fighter,hauler,stations,weapons (--list-classes shows the names)")
    ap.add_argument("--list-classes", action="store_true", help="list the ship classes and stop")
    ap.add_argument("--config", help="a settings file (default: config.json next to this script, when there is one)")
    ap.add_argument("--out", default=os.path.join(HERE, "nms_ships"), help="where the mod goes (default: nms_ships next to this script)")
    ap.add_argument("--max-texture", type=int, default=2048, help="the textures' longest side (default 2048; 1024 for phones)")
    ap.add_argument("--max-variants", type=int, default=4, help="variants of one part over its nested options (default 4)")
    ap.add_argument("--max-parts", type=int, default=14, help="parts per slot at most (default 14)")
    ap.add_argument("--limit-parts", type=int, help="parts per slot for a quick test build")
    ap.add_argument("--transitions", choices=("pose", "loop", "rest"), default="pose",
                    help="the parts that swing out for flight (wings, engines): pose = shown in their flying pose (default); "
                         "loop = their take-off and landing played in a loop; rest = as modelled (the landed pose)")
    ap.add_argument("--no-animations", action="store_true", help="no animations: no spinning turbines, no idle loops, the landed pose")
    ap.add_argument("--no-part-stats", action="store_true", help="no stat bonuses from the parts' sizes (big wings carry more, big engines go faster)")
    ap.add_argument("--zip", action="store_true", help="also zip the mod")
    ap.add_argument("--fresh", action="store_true", help="delete the output folder first")
    ap.add_argument("--verbose", action="store_true", help="print the build's notes (triangle counts, LOD floors, turns)")
    first, _ = ap.parse_known_args()
    config = os.path.abspath(os.path.expanduser(first.config)) if first.config else CONFIG
    if first.config and not os.path.exists(config):
        fail(f"no settings file at {config}")
    ap.set_defaults(**load_config(config, ap))
    a = ap.parse_args()
    check_python()
    import build
    from nms import hgpak
    import weapons
    import world
    if a.list_classes:
        for k, v in build.CLASSES.items():
            print(f"  {k:20} {v['name']}: {v['description']}" + ("" if "proc" in v else "  (a hostile craft in the traffic)" if v.get("traffic_only") else "  (a fixed design)"))
        for k, v in build.CAPITALS.items():
            print(f"  {k:20} {v['name']}: {v['description']}  (a capital ship in the traffic)")
        for k, v in world.STATIONS.items():
            print(f"  {k:20} {v['name']}  (a station model, {v['scene']})")
        for w in weapons.WEAPONS:
            print(f"  {w['id']:20} a ship weapon ({w['tech']})")
        print("  all                  everything; procedural = the customizable classes; fixed = the fixed designs; hostile = the hostile craft;\n"
              "  capitals = the capital ships; stations = the stations and their systems; weapons = the ship weapons")
        return
    if not a.game:
        ap.error(f"give the game folder (or \"game\" in {os.path.basename(config)})")
    banks_folder = hgpak.find_banks(a.game)
    if not banks_folder:
        fail(f"no PCBANKS or IOSBANKS folder with .pak archives under {a.game}")
    groups = {"procedural": [c for c, v in build.CLASSES.items() if "proc" in v],
              "fixed": [c for c, v in build.CLASSES.items() if "scene" in v and not v.get("traffic_only")],
              "hostile": [c for c, v in build.CLASSES.items() if v.get("traffic_only")],
              "capitals": list(build.CAPITALS), "stations": ["stations"], "weapons": ["weapons"]}
    groups["all"] = [c for g in ("procedural", "fixed", "hostile", "capitals", "stations", "weapons") for c in groups[g]]
    classes = []
    for c in ("all" if a.classes in ("all", "") else a.classes).split(","):
        c = c.strip()
        if c:
            classes.extend(groups.get(c, [c]))
    known = set(build.CLASSES) | set(build.CAPITALS) | set(world.STATIONS) | {w["id"] for w in weapons.WEAPONS} | {"stations", "weapons"}
    unknown = [c for c in classes if c not in known]
    if unknown:
        fail(f"unknown classes: {', '.join(unknown)} (--list-classes lists them)")
    out = os.path.abspath(os.path.expanduser(a.out))
    if a.fresh and os.path.isdir(out):
        import shutil
        shutil.rmtree(out)
    if os.path.exists(config):
        print(f"Settings: {config}")
    banks = hgpak.Banks(banks_folder)
    print(f"No Man's Sky archives: {banks_folder} ({banks.platform})")
    build.MAX_VARIANTS = a.max_variants
    build.MAX_PARTS_PER_SLOT = a.max_parts
    build.TRANSITIONS = a.transitions
    build.ANIMATIONS = not a.no_animations
    build.PART_STATS = not a.no_part_stats
    try:
        kits, ships, report = build.build(banks, out, classes, limit_parts=a.limit_parts, max_texture=a.max_texture)
    except hgpak.MissingCodec as e:
        fail(str(e))
    if a.zip:
        z = build.zip_mod(out, out + ".zip")
        print(f"Zipped: {z}")
    if a.verbose:
        for n in report.notes:
            print("  note: " + n)
    if report.warnings:
        print(f"{len(report.warnings)} warnings (above).")


if __name__ == "__main__":
    main()
