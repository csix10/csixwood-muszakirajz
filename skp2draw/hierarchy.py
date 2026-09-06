"""
Komponens-típus osztályozás: panel (sík bútorlap) vs lakatszerelvény (hardware),
és az egyedi méretű panel-változatok összegyűjtése a rajzgeneráláshoz.
"""
from __future__ import annotations
from skp2draw.parser.model import Node
from skp2draw.geometry.bbox import scaled_local_sizes
from skp2draw.geometry.bbox import scaled_local_sizes, subtree_bbox_in_frame

PANEL_MIN_FACE_SIZE_MM = 100.0


def classify_kind(node: Node) -> str:
    """Visszaadja: 'panel', 'hardware', vagy 'no_geometry'."""
    sizes = scaled_local_sizes(node)
    if sizes is None:
        return "no_geometry"
    sorted_sizes = sorted(sizes, reverse=True)
    if sorted_sizes[1] >= PANEL_MIN_FACE_SIZE_MM:
        return "panel"
    return "hardware"


def collect_unique_panels(root: Node):
    """
    Bejárja a fát, és minden EGYEDI MÉRETŰ panel-változatból egy
    reprezentáns Node-ot ad vissza, a példányszámmal együtt.

    FONTOS: ugyanaz a definíció-név (pl. 'Oldal#1') a modellben többször,
    de KÜLÖNBÖZŐ TÉNYLEGES MÉRETBEN is előfordulhat - egy közös "mester"
    sablon-alakzatot használva, amit az egyes szekrényekhez különböző
    méretre nyújtanak/zsugorítanak (lásd: scaled_local_sizes). Ezért NEM
    elég a definíció neve szerint deduplikálni: minden EGYEDI (név, méret)
    pár egy KÜLÖN fizikai alkatrész, aminek KÜLÖN rajz kell, különben
    legyártatlan alkatrészek maradnának ki a listából.

    Visszaad: lista (Node, darabszám) párokról.
    """
    seen: dict[tuple, tuple[Node, int]] = {}

    def walk(node: Node):
        if node.has_geometry and classify_kind(node) == "panel":
            sizes = scaled_local_sizes(node)
            size_key = tuple(round(s, 1) for s in sorted(sizes))
            key = (node.definition_name, size_key)
            if key in seen:
                existing_node, count = seen[key]
                seen[key] = (existing_node, count + 1)
            else:
                seen[key] = (node, 1)
        for c in node.children:
            walk(c)

    walk(root)
    return list(seen.values())

def _has_panel_descendant(node: Node) -> bool:
    """Van-e a node részfájában legalább egy panelként osztályozott elem."""
    if node.has_geometry and classify_kind(node) == "panel":
        return True
    return any(_has_panel_descendant(c) for c in node.children)


def _count_geometry_descendants(node: Node) -> int:
    """Hány geometriával rendelkező (panel VAGY hardware) leszármazott van."""
    n = 1 if node.has_geometry else 0
    for c in node.children:
        n += _count_geometry_descendants(c)
    return n


MIN_PARTS_FOR_ASSEMBLY = 2


def collect_unique_assemblies(root: Node):
    """
    A root KÖZVETLEN gyerekei közül azokat gyűjti össze, amik VALÓDI
    ÖSSZEÁLLÍTÁSOK (nincs saját geometriájuk - tehát csoport/komponens
    konténerek -, de van legalább egy panel-leszármazottjuk, és legalább
    MIN_PARTS_FOR_ASSEMBLY db geometriával rendelkező leszármazottjuk).

    Az egyedi (név, méret) párok szerint deduplikál, példányszámmal együtt.
    Visszaad: lista (Node, darabszám) párokról.
    """
    seen: dict[tuple, tuple[Node, int]] = {}

    for node in root.children:
        if node.has_geometry:
            continue
        if not _has_panel_descendant(node):
            continue
        if _count_geometry_descendants(node) < MIN_PARTS_FOR_ASSEMBLY:
            continue

        bbox = subtree_bbox_in_frame(node, node.world_matrix)
        if bbox is None:
            continue
        mins, maxs = bbox
        size_key = tuple(round(s, 1) for s in (maxs - mins))
        key = (node.definition_name, size_key)

        if key in seen:
            existing_node, count = seen[key]
            seen[key] = (existing_node, count + 1)
        else:
            seen[key] = (node, 1)

    return list(seen.values())