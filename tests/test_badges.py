"""
Tesztek a badges.py CSV-beolvasásához és a hierarchy.py Badges-alapú
komponens-szűrőjéhez (_has_badge_descendant, collect_unique_assemblies).
"""
from __future__ import annotations
import numpy as np

from skp2draw.badges import load_badge_keys
from skp2draw.parser.model import Node, Mesh
from skp2draw.hierarchy import _has_badge_descendant, _node_badge_key, collect_unique_assemblies


SAMPLE_CSV = (
    "No.;Designation;Quantity;Length - raw;Width - raw;Thickness - raw;"
    "Length;Width;Thickness;Area - final;Type;Material;Material description;"
    "URL of the material;Instance names;Description;URL;Badges;"
    "Edge Length 1;Edge Length 2;Edge Width 1;Edge Width 2;Frontside;"
    "Backside;Tags\n"
    'A;Munkalap;1;1840 mm;635 mm;38 mm;1840 mm;635 mm;38 mm;"";Undefined;'
    '107FS15;"";"";"";"";"";munkalap;"";"";"";"";"";"";Layer0\n'
    'B;Ajtó_1;2;716 mm;596 mm;18 mm;716 mm;596 mm;18 mm;"";Undefined;'
    'fogmart A36/R3 Net 62;"";"";"";"";"";MDF;"";"";"";"";"";"";Layer0\n'
    'A;Dishwasher;1;870 mm;600 mm;450 mm;870 mm;600 mm;450 mm;"";Undefined;'
    '<auto>2;"";"";"";"Parametric freestanding dishwasher.\n\n'
    'Multi-line description continues here.";"";"";"";"";"";"";"";"";Layer0\n'
)


def test_load_badge_keys_parses_semicolon_csv(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")

    keys = load_badge_keys(csv_path)

    # Munkalap és Ajtó_1 badge-elve vannak (nem üres Badges) -> bekerülnek
    assert ("Munkalap", (38.0, 635.0, 1840.0)) in keys
    assert ("Ajtó_1", (18.0, 596.0, 716.0)) in keys

    # A Dishwasher-nek üres a Badges oszlopa (és a leírása több sorba
    # ágyazott, idézőjeles mező - ez sem téveszti meg a beolvasást)
    assert not any(name == "Dishwasher" for name, _ in keys)
    assert len(keys) == 2


def _make_box_node(name: str, size_mm) -> Node:
    """Egyszerű, nem-üres geometriájú Node egy dobozzal, tesztekhez."""
    sx, sy, sz = size_mm
    vertices = np.array([
        [0, 0, 0], [sx, 0, 0], [sx, sy, 0], [0, sy, 0],
        [0, 0, sz], [sx, 0, sz], [sx, sy, sz], [0, sy, sz],
    ], dtype=np.float64)
    faces = [(0, 1, 2), (0, 2, 3), (4, 5, 6)]
    mesh = Mesh(vertices_mm=vertices, faces=faces)
    identity = np.eye(4)
    return Node(
        name=name, definition_name=name,
        local_matrix=identity, world_matrix=identity,
        mesh=mesh, children=[],
    )


def _make_container_node(name: str, children) -> Node:
    identity = np.eye(4)
    return Node(
        name=name, definition_name=name,
        local_matrix=identity, world_matrix=identity,
        mesh=None, children=children,
    )


def test_has_badge_descendant_true_for_direct_leaf_match():
    door = _make_box_node("Ajtó_1", (716, 596, 18))
    badge_keys = {("Ajtó_1", (18.0, 596.0, 716.0))}
    assert _has_badge_descendant(door, badge_keys)


def test_has_badge_descendant_true_for_nested_match():
    panel = _make_box_node("Oldal#1", (940, 320, 18))
    module = _make_container_node("also_60-as_fiokos", [panel])
    badge_keys = {("Oldal#1", (18.0, 320.0, 940.0))}
    assert _has_badge_descendant(module, badge_keys)


def test_node_badge_key_reflects_stretched_world_scale():
    """
    A modellek gyakran egy közös "mester" sablon-alakzatot (pl. egy 2000mm
    hosszú munkalap-sablont) nyújtanak/zsugorítanak az egyes szekrényekhez
    - ez a node SAJÁT world_matrix-ában egy nem-egyenletes skálázásként
    jelenik meg. A badge-kulcsnak a TÉNYLEGES, nyújtott méretet kell
    tükröznie (hogy egyezzen az OpenCutList CSV végleges méretével), NEM
    a nyújtás előtti sablon-méretet.
    """
    sablon = _make_box_node("Munkalap", (2000, 600, 38))
    # A hossz-tengelyt (X) 1.798x-re nyújtjuk: 2000mm -> 3596mm.
    scale = np.diag([1.798, 1.0, 1.0, 1.0])
    sablon.world_matrix = scale @ sablon.world_matrix

    key = _node_badge_key(sablon)

    assert key == ("Munkalap", (38.0, 600.0, 3596.0))


def test_has_badge_descendant_false_when_no_match():
    fridge_part = _make_box_node("Hűtő", (658, 2030, 595))
    badge_keys = {("Munkalap", (38.0, 635.0, 1840.0))}
    assert not _has_badge_descendant(fridge_part, badge_keys)


def test_collect_unique_assemblies_with_badge_keys_excludes_standalone_leaf():
    """
    Egy önmagában, egyetlen lapból álló root-gyerek (pl. egy önálló ajtó
    vagy munkalap-szegmens) a Badges-alapú szabállyal SEM számít
    "összeállításnak" (bútorelemnek) - ezt már a panel-szintű lista
    (collect_unique_panels) helyesen, a valós (esetleg nyújtott) méretével
    lefedi. Az assembly_construction_views ugyanis a node SAJÁT
    world_matrix-át használja keretként, ami egy ilyen, saját maga
    nyújtott/skálázott levél-node esetén a saját skálázását kioltaná, és
    mindig a nyújtás előtti sablon-méretet rajzolná ki tévesen - ezért
    (csakúgy, mint a régi, badge nélküli heurisztikánál) itt is kihagyjuk.
    """
    door = _make_box_node("Ajtó_1", (716, 596, 18))
    root = _make_container_node("root", [door])
    badge_keys = {("Ajtó_1", (18.0, 596.0, 716.0))}

    assemblies = collect_unique_assemblies(root, badge_keys)

    assert assemblies == []


def test_collect_unique_assemblies_with_badge_keys_excludes_unbadged_appliance():
    """
    Egy több geometria-részből álló, de a CSV-ben Badges NÉLKÜL szereplő
    elem (pl. egy mosogatógép/hűtő) a RÉGI, darabszám-alapú szabály
    szerint tévesen bekerült - a Badges-alapú szabálynak ki kell zárnia.
    """
    part_a = _make_box_node("Dishwasher_part_a", (500, 300, 20))
    part_b = _make_box_node("Dishwasher_part_b", (500, 300, 20))
    appliance = _make_container_node("Dishwasher", [part_a, part_b])
    root = _make_container_node("root", [appliance])
    badge_keys = {("Munkalap", (38.0, 635.0, 1840.0))}

    assemblies = collect_unique_assemblies(root, badge_keys)

    assert assemblies == []


def test_collect_unique_assemblies_without_badge_keys_keeps_old_behavior():
    """
    badge_keys=None esetén a RÉGI (legalább 2 alkatrészből álló
    összeállítás) heurisztika marad érvényben - visszafelé kompatibilitás
    a CSV nélküli használathoz.
    """
    panel_a = _make_box_node("Oldal#1", (940, 320, 18))
    panel_b = _make_box_node("Alja", (600, 560, 18))
    module = _make_container_node("also_60-as_fiokos", [panel_a, panel_b])
    root = _make_container_node("root", [module])

    assemblies = collect_unique_assemblies(root, badge_keys=None)

    assert len(assemblies) == 1
    assert assemblies[0][0].definition_name == "also_60-as_fiokos"