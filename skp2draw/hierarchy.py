"""
Komponens-típus osztályozás: panel (sík bútorlap) vs lakatszerelvény (hardware),
és az egyedi méretű panel-változatok összegyűjtése a rajzgeneráláshoz.
"""
from __future__ import annotations
from skp2draw.parser.model import Node
from skp2draw.geometry.bbox import scaled_local_sizes

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