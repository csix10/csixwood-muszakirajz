"""
Komponens-típus osztályozás: panel (sík bútorlap) vs lakatszerelvény (hardware),
és az egyedi méretű panel-változatok / bútorelem-modulok összegyűjtése a
rajzgeneráláshoz.
"""
from __future__ import annotations
from skp2draw.parser.model import Node
from skp2draw.geometry.bbox import scaled_local_sizes, subtree_bbox_in_frame

PANEL_MIN_FACE_SIZE_MM = 100.0
PANEL_MAX_THICKNESS_MM = 50.0


def classify_kind(node: Node) -> str:
    """
    Visszaadja: 'panel', 'hardware', vagy 'no_geometry'.

    A "két nagy méret" szabály önmagában tévesen panelnek nézne nagyobb,
    de nem lapszerű dolgokat is (pl. egy egész szoba-csoportot, egy hűtőt,
    egy komplex polcrendszert) - ezért egy felső vastagság-korlátot is
    előírunk: egy valódi bútorlap tipikusan legfeljebb ~40mm vastag,
    biztonsági ráadással 50mm-ig engedjük.
    """
    sizes = scaled_local_sizes(node)
    if sizes is None:
        return "no_geometry"
    sorted_sizes = sorted(sizes, reverse=True)
    thickness = sorted_sizes[2]
    if sorted_sizes[1] >= PANEL_MIN_FACE_SIZE_MM and thickness <= PANEL_MAX_THICKNESS_MM:
        return "panel"
    return "hardware"


def find_parent(root: Node, target: Node) -> Node | None:
    """
    Megkeresi `target` KÖZVETLEN szülőjét a fában (identitás szerint, `is`
    - nem érték-egyezés). Erre azért van szükség, mert a Node-fa csak
    lefelé (children) tárol referenciát, felfelé (szülő) nem - pedig egy
    adott panel-példány "modulját" (a szekrény-csoportot, aminek a
    gyereke/leszármazottja) csak így tudjuk visszakeresni, hogy aztán meg
    tudjuk találni a VELE EGY MODULBAN lévő kötőelemeket (lásd:
    skp2draw.geometry.projection.find_touching_hardware).

    Visszaad None-t, ha `target` maga a `root`, vagy nem található.
    """
    for child in root.children:
        if child is target:
            return root
        found = find_parent(child, target)
        if found is not None:
            return found
    return None


def collect_unique_panels(root: Node, badge_keys: set | None = None):
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

    Ha `badge_keys` meg van adva (lásd: skp2draw.badges.load_badge_keys),
    csak azok a panel-változatok kerülnek be, amiknek a (definíció-név,
    méret) párja szerepel a CSV-ben NEM ÜRES Badges-szel. Enélkül a
    "két nagy méret, kis vastagság" geometriai szabály (classify_kind)
    tévesen alkatrésznek nézne olyan, nem vágandó lapszerű dolgokat is,
    amik valójában egy konyhai gép része (pl. egy főzőlap üveglapja) -
    ezeket sosem címkézed meg az OpenCutList-ben, tehát nincs Badges-ük.

    Ha `badge_keys` None (nincs megadva CSV), minden panelként
    osztályozott elem bekerül - visszafelé kompatibilitás.

    Visszaad: lista (Node, darabszám) párokról.
    """
    seen: dict[tuple, tuple[Node, int]] = {}

    def walk(node: Node):
        if node.has_geometry and classify_kind(node) == "panel":
            sizes = scaled_local_sizes(node)
            size_key = tuple(round(s, 1) for s in sorted(sizes))
            key = (node.definition_name, size_key)
            if badge_keys is None or key in badge_keys:
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


def _node_size_key(node: Node) -> tuple[float, float, float] | None:
    """
    A node SAJÁT (leszármazott nélküli, csak a saját mesh-éből számolt)
    mérete, RENDEZETT (növekvő) hármasként.

    FONTOS: ugyanazt a `scaled_local_sizes`-t használja, mint
    `classify_kind`/`collect_unique_panels` - vagyis a node saját HELYI
    (skálázatlan) bbox-át megszorozza a világmátrix skálázó részével.
    Ez azért lényeges, mert sok elem (pl. egy munkalap) egy közös
    "mester" sablon-alakzatot használ, amit a világmátrix nem egyenletes
    skálázással nyújt/zsugorít a tényleges méretre (pl. 2000mm-es sablon
    -> 3596mm-es nyújtott munkalap). A KORÁBBI implementáció
    (`subtree_bbox_in_frame(node, node.world_matrix)`) a pontokat a NODE
    SAJÁT keretébe vetítette vissza, ami éppen a node SAJÁT skálázását
    oltja ki - ezért mindig a nyújtás ELŐTTI (sablon-)méretet adta
    vissza, és a CSV-ben rögzített, ténylegesen nyújtott méret sosem
    egyezett - lásd: a munkalap hiányzott az áttekintő rajzról.

    A rendezés azért kell, hogy a badges.load_badge_keys által beolvasott
    CSV Length/Width/Thickness hármasával össze lehessen hasonlítani,
    függetlenül attól, hogy az OpenCutList és a modellünk ugyanazt a
    tengelyt hívja-e "hossznak"/"szélességnek"/"vastagságnak".
    """
    sizes = scaled_local_sizes(node)
    if sizes is None:
        return None
    return tuple(round(s, 1) for s in sorted(sizes))


def _node_badge_key(node: Node) -> tuple[str, tuple[float, float, float]] | None:
    """A node (definíció-név, rendezett méret) párja - lásd _node_size_key."""
    size = _node_size_key(node)
    if size is None:
        return None
    return (node.definition_name, size)


def _has_badge_descendant(node: Node, badge_keys: set) -> bool:
    """
    Van-e a node részfájában (ÖNMAGÁT is beleértve) legalább egy olyan
    geometriával rendelkező elem, aminek a (definíció-név, méret) párja
    szerepel a badge_keys halmazban - vagyis amit Te ténylegesen
    megcímkéztél (nem üres Badges) az OpenCutList-ben.

    Ez az EGYETLEN megbízható jel arra, hogy egy elemet valóban
    legyártásra szánt, kész alkatrésznek/terméknek tekintesz - nem egy
    geometriai heurisztika (pl. "hány alkatrészből áll", ami tévesen
    bevette a sok geometria-résszel modellezett konyhai gépeket, és
    tévesen kihagyta az önmagukban egyetlen lapból álló, de valódi
    elemeket, pl. egy önálló ajtót vagy munkalap-szegmenst).
    """
    if node.has_geometry:
        key = _node_badge_key(node)
        if key is not None and key in badge_keys:
            return True
    return any(_has_badge_descendant(c, badge_keys) for c in node.children)


def collect_unique_assemblies(root: Node, badge_keys: set | None = None):
    """
    A root KÖZVETLEN gyerekei közül azokat gyűjti össze, amik VALÓDI,
    a modellhez tartozó elemek (a "bútorelem" szintű rajzokhoz).

    Ha `badge_keys` meg van adva (lásd: skp2draw.badges.load_badge_keys),
    a szűrés TELJESEN ezen alapul: egy root-gyerek csak akkor számít
    "valódi elemnek", ha Ő MAGA, VAGY BÁRMELYIK leszármazottja olyan
    (definíció-név, méret) párral rendelkezik, ami a CSV-ben NEM ÜRES
    Badges-szel szerepel - vagyis Te ténylegesen megcímkézted az
    OpenCutList-ben. Ez azért jobb, mint a régi, geometria-alapú szabály,
    mert az tévesen bevette a több geometria-résszel modellezett konyhai
    gépeket (pl. hűtő, mosogatógép), és tévesen kihagyta az önmagukban
    egyetlen lapból álló, de valódi, legyártandó elemeket (önálló ajtó,
    munkalap-szegmens).

    Ha `badge_keys` None (nincs megadva CSV), a RÉGI heurisztika marad
    érvényben (visszafelé kompatibilitás): nincs saját geometriája, van
    legalább egy panel-leszármazottja, és legalább MIN_PARTS_FOR_ASSEMBLY
    db geometriával rendelkező leszármazottja.

    Az egyedi (név, méret) párok szerint deduplikál, példányszámmal együtt.
    Visszaad: lista (Node, darabszám) párokról.
    """
    seen: dict[tuple, tuple[Node, int]] = {}

    for node in root.children:
        # Egy root-gyerek, aminek MAGÁNAK van geometriája (nincs saját
        # leszármazottja - pl. egy önálló munkalap-szegmens vagy ajtó,
        # amit a badge-szűrő önmagában talál el), NEM "bútorelem"
        # (összeállítás), hanem egyetlen panel - azt már a panel-szintű
        # lista (collect_unique_panels) helyesen, a valós (nyújtott)
        # méretével kezeli. Az `assembly_construction_views` (aminek a
        # frame-je node.world_matrix) ilyen esetben a node SAJÁT
        # skálázását oltaná ki, és mindig a nyújtás előtti sablon-méretet
        # rajzolná ki - ezért itt, csakúgy mint a régi (badge nélküli)
        # heurisztikánál, kihagyjuk.
        if node.has_geometry:
            continue

        if badge_keys is not None:
            if not _has_badge_descendant(node, badge_keys):
                continue
        else:
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