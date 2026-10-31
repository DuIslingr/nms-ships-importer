"""Procedural models' descriptors (.DESCRIPTOR.MBIN): the slots of a ship class and the options in each.

A descriptor is a list of groups; a group has a type id (`_COCKPIT_`, `_WINGS_`: the slot) and descriptors (the
options: id `_WINGS_F`, name `_Wings_F` = the scene node that shows for it, a chance weight, reference paths, and its own
nested groups: the slots that exist only when this option is picked, `_ACC_` under `_WINGS_F`). The game picks one
option per group from a seed; this module lists them and turns a pick into the set of scene node names that show.
"""
from . import mbin


class Option:
    __slots__ = ("id", "name", "chance", "references", "groups", "group")

    def __init__(self, raw, group):
        self.id = raw["id"]
        self.name = raw["name"] or raw["id"]
        self.chance = raw["chance"]
        self.references = raw["reference_paths"]
        self.group = group
        self.groups = []
        for child, _ in raw["children"]:
            if child:
                self.groups.extend(Group(g, self) for g in child["list"])

    @property
    def is_none(self):
        """An option that shows nothing (`_ACC_NONE3`, `_UWING_NULL`)."""
        u = self.id.upper()
        return "NONE" in u or "NULL" in u

    @property
    def slot(self):
        return self.group.slot

    def __repr__(self):
        return f"Option({self.id})"


class Group:
    __slots__ = ("type_id", "options", "parent")

    def __init__(self, raw, parent=None):
        self.type_id = raw["type_id"]
        self.parent = parent
        self.options = [Option(o, self) for o in raw["descriptors"]]

    @property
    def slot(self):
        """`_WINGS_` -> 'wings'."""
        return self.type_id.strip("_").lower()

    @property
    def depth(self):
        d, g = 0, self
        while g.parent is not None:
            d += 1
            g = g.parent.group
        return d

    def __repr__(self):
        return f"Group({self.type_id}, {len(self.options)})"


class Descriptor:
    def __init__(self, data):
        _, raw = mbin.load(data, "TkModelDescriptorList")
        self.groups = [Group(g) for g in raw["list"]]

    def walk(self):
        """Every group, depth first."""
        stack = list(reversed(self.groups))
        while stack:
            g = stack.pop()
            yield g
            for o in g.options:
                stack.extend(reversed(o.groups))

    @property
    def option_names(self):
        """The lower-cased scene node names of every option, at every depth."""
        return {o.name.lower() for g in self.walk() for o in g.options}


def lod_twin(option, group):
    """Whether the option is only a coarser LOD of another option of its group (`_frontfeet_BLOD1` beside
    `_frontfeet_BLOD0`): the game lists each LOD of some meshes as an option of its own."""
    import re
    m = re.match(r"(.*)lod([1-9]\d*)$", option.name, re.I)
    if not m:
        return False
    return any(o is not option and re.fullmatch(re.escape(m.group(1)) + r"lod0", o.name, re.I) for o in group.options)


def chooser(descriptor, picks):
    """A `choose(node)` for scene.Assembler: a node named like an option shows only when it is in `picks` (a set of
    option ids or names, lower case); every other node shows."""
    import re
    lod = re.compile(r"lod\d+$", re.I)
    names = {}
    for g in descriptor.walk():
        for o in g.options:   # an option named for a mesh's LOD0 covers its LOD siblings; some list each LOD as an option
            names.setdefault(lod.sub("", o.name.lower()), []).append(o)
    picked = {p.lower() for p in picks}

    def choose(node):
        options = names.get(lod.sub("", node.name.lower()))
        if options is None:
            return True
        return any(o.id.lower() in picked or o.name.lower() in picked for o in options)
    return choose


def likeliest(group):
    """The group's option with the highest chance (a 'none' counts: the game then usually shows nothing there); on a
    tie the first that isn't a 'none'. None for an empty group."""
    if not group.options:
        return None
    top = max(o.chance for o in group.options)
    tied = [o for o in group.options if o.chance >= top - 1e-9]
    return next((o for o in tied if not o.is_none), tied[0])


def default_picks(group, chosen=None):
    """One option per group, the likeliest, recursively: the game's commonest look, more or less."""
    chosen = chosen if chosen is not None else set()
    o = likeliest(group)
    if o is None:
        return chosen
    chosen.add(o.id.lower())
    for g in o.groups:
        default_picks(g, chosen)
    return chosen
