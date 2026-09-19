"""
Egy panel-komponens három nézetének (elölnézet, felülnézet, oldalnézet)
DXF rajzzá alakítása: téglalapok, VALÓDI méretvonalakkal (nyilakkal és
felirattal), ahogy egy tényleges műszaki rajzon. Emellett a teljes
konyha elrendezés-rajzának (alaprajz) exportja is itt van.
"""
from __future__ import annotations
from pathlib import Path
import ezdxf

from skp2draw.geometry.bbox import subtree_world_bbox
from skp2draw.hierarchy import (
    _has_panel_descendant,
    _count_geometry_descendants,
    _has_badge_descendant,
    MIN_PARTS_FOR_ASSEMBLY,
)
from skp2draw.geometry.projection import assembly_construction_views, layout_axes, layout_view_specs, full_layout_views
from skp2draw.geometry.hidden_line import compute_visible_segments
from skp2draw.dimensioning.rules import rectangle_dimensions, chain_dimensions, edge_distance_dimensions
from skp2draw.dimensioning.dimension_line import DimensionLine

GAP_MM = 60.0
TITLE_HEIGHT_MM = 12.0
LABEL_HEIGHT_MM = 8.0
DIM_OFFSET_MM = 15.0

DIMSTYLE_NAME = "MUSZAKI"

# A méretvonal-szöveg/nyíl mérete (mm) egy adott rajzhoz `scale`-lel van
# felszorozva - lásd _text_scale_for_extent: egy alkatrész-rajz (pár száz
# mm) esetén scale=1.0 marad (ez volt eddig is jó), de egy bútorelem- vagy
# a teljes-konyha áttekintő rajznál (több ezer mm) enélkül a szöveg a lap
# méretéhez képest olvashatatlanul picire zsugorodna, hiszen a rajz vég-
# eredményben mindig ugyanarra az A4 oldalra kerül, függetlenül attól,
# hogy pár száz vagy több ezer mm-t ábrázol.
REFERENCE_EXTENT_MM = 700.0
MAX_TEXT_SCALE = 6.0


def _text_scale_for_extent(extent_mm: float) -> float:
    """
    Mekkorára kell nagyítani a méretvonal-szöveget/nyilakat egy `extent_mm`
    (a rajz nagyobbik kiterjedése) méretű rajzhoz, hogy a szöveg a
    kinyomtatott A4 oldalon nagyjából ugyanakkorának tűnjön, mint egy
    átlagos (REFERENCE_EXTENT_MM körüli) alkatrész-rajzon. Sosem kicsinyít
    (kisebb rajzoknál 1.0 marad), és egy ésszerű felső korlátig nagyít.
    """
    if extent_mm <= REFERENCE_EXTENT_MM:
        return 1.0
    return min(MAX_TEXT_SCALE, extent_mm / REFERENCE_EXTENT_MM)


def _ensure_dimstyle(doc, scale: float = 1.0):
    """
    Az ezdxf alapértelmezett méretstílusa (dimtxt=0.25, dimasz=0.175) egy
    "egységnyi" rajzhoz van hangolva - nálunk viszont a rajzi egység = 1 mm,
    és a modell többszáz mm, szóval saját, a rajz méretéhez illő stílust
    definiálunk (mm-es szöveg- és nyílméretekkel), `scale`-lel felszorozva
    (lásd _text_scale_for_extent).
    """
    if DIMSTYLE_NAME in doc.dimstyles:
        return
    style = doc.dimstyles.new(DIMSTYLE_NAME)
    style.dxf.dimtxt = 10.0 * scale   # szöveg magassága, mm
    style.dxf.dimasz = 8.0 * scale    # nyílvégződés mérete, mm
    style.dxf.dimexe = 5.0 * scale    # segédvonal túlnyúlása a méretvonalon
    style.dxf.dimexo = 3.0 * scale    # segédvonal távolsága a mért ponttól
    style.dxf.dimgap = 2.0 * scale    # rés a méretvonal és a szöveg között
    style.dxf.dimdec = 0              # minden méret EGÉSZ mm-re kerekítve jelenjen meg

def _render_dimension_lines(msp, dims):
    for dim in dims:
        angle = 0 if dim.kind == "horizontal" else 90
        dxf_dim = msp.add_linear_dim(
            base=dim.base, p1=dim.p1, p2=dim.p2, angle=angle,
            dimstyle=DIMSTYLE_NAME,
        )
        dxf_dim.render()

def _add_rectangle(msp, x0, y0, width, height):
    points = [
        (x0, y0), (x0 + width, y0),
        (x0 + width, y0 + height), (x0, y0 + height),
    ]
    msp.add_lwpolyline(points, close=True)


def _add_dimensions(msp, x0, y0, width, height):
    _render_dimension_lines(msp, rectangle_dimensions(x0, y0, width, height, offset=DIM_OFFSET_MM))

def _add_hardware_polygons(msp, hardware_polys, x_offset=0.0, y_offset=0.0):
    for hw in hardware_polys:
        points = [(u + x_offset, v + y_offset) for u, v in hw["points"]]
        linetype = "Continuous" if hw["visible"] else "DASHED"
        msp.add_lwpolyline(points, close=True, dxfattribs={"linetype": linetype})


def export_views(views, label: str, path, count: int = 1, hardware_by_view: dict | None = None):
    """
    `hardware_by_view`: opcionális {nézet_label: [hardver-overlay, ...]}
    (lásd: skp2draw.geometry.projection.panel_hardware_overlays) - az
    adott panelt ÉRINTŐ kötőelemek körvonala MINDHÁROM nézeten, PLUSZ
    minden kötőelemhez (nézetenként) két méretvonal (a középpontjától a
    legközelebbi függőleges, illetve vízszintes alkatrész-élig, lásd:
    skp2draw.dimensioning.rules.edge_distance_dimensions - a 0mm-re
    kerekedő méretvonalakat ez már automatikusan kihagyja), hogy a
    furat/rögzítés pontos pozíciója mindhárom nézeten leolvasható legyen.
    """
    doc = ezdxf.new(setup=True)
    _ensure_dimstyle(doc)
    msp = doc.modelspace()
    hardware_by_view = hardware_by_view or {}

    # A három nézet EGYMÁS ALATT kerül a lapra (nem egymás mellett) - így
    # egy A4 álló oldalon nagyobbra vehető mindegyik. `floor`: az eddig
    # felhasznált terület ALJA (a legutóbbi nézet felirata alatt) - a
    # KÖVETKEZŐ nézet origóját ennek és a SAJÁT magasságának
    # figyelembevételével kell elhelyezni, KÜLÖNBEN egy alacsonyabb nézet
    # után egy magasabb nézet visszanyúlna, és átfedésbe kerülne az
    # előzővel.
    floor = None
    title_top = None
    for v in views:
        y_cursor = 0.0 if floor is None else floor - GAP_MM - v.height

        _add_rectangle(msp, 0.0, y_cursor, v.width, v.height)
        _add_dimensions(msp, 0.0, y_cursor, v.width, v.height)

        hw_list = hardware_by_view.get(v.label, [])
        _add_hardware_polygons(msp, hw_list, x_offset=0.0, y_offset=y_cursor)
        for hw in hw_list:
            for dim in edge_distance_dimensions(v.width, v.height, hw["center"]):
                shifted = DimensionLine(
                    kind=dim.kind,
                    p1=(dim.p1[0], dim.p1[1] + y_cursor),
                    p2=(dim.p2[0], dim.p2[1] + y_cursor),
                    base=(dim.base[0], dim.base[1] + y_cursor),
                    value=dim.value,
                )
                _render_dimension_lines(msp, [shifted])

        label_y = y_cursor - DIM_OFFSET_MM - LABEL_HEIGHT_MM * 4
        msp.add_text(
            v.label,
            dxfattribs={"height": LABEL_HEIGHT_MM},
        ).set_placement((0.0, label_y))

        if title_top is None:
            title_top = y_cursor + v.height
        floor = label_y - LABEL_HEIGHT_MM

    title = label if count == 1 else f"{label}  ({count} db)"
    msp.add_text(
        title,
        dxfattribs={"height": TITLE_HEIGHT_MM},
    ).set_placement((0.0, title_top + DIM_OFFSET_MM + TITLE_HEIGHT_MM * 3))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))


# ('export_panel_views' régi név megtartása visszafelé kompatibilitáshoz)
export_panel_views = export_views


# ---- Teljes elrendezés / áttekintő rajz ----
#
# Cél: nem egy-egy bútorelem szerkezete, hanem a TELJES bútorzat, hogy
# lássuk, az egyes modulok hol állnak egymáshoz képest - fő méretekkel
# (modulhatárok + össz-méret), nem a részletes belső szerkezettel.

LAYOUT_CHAIN_OFFSET_MM = 40.0
LAYOUT_OVERALL_OFFSET_MM = 120.0
LAYOUT_VIEW_GAP_MM = 800.0
MODULE_LABEL_HEIGHT_MM = 12.0


def _collect_layout_modules(root, badge_keys=None):
    """
    A root közvetlen gyerekei közül a VALÓDI, a modellhez tartozó
    elemeket gyűjti össze, a VILÁG-koordinátás befoglaló dobozukkal
    (mins, maxs) együtt - ez adja meg minden modul TÉNYLEGES, egymáshoz
    képesti helyzetét.

    Ha `badge_keys` meg van adva (skp2draw.badges.load_badge_keys), a
    szűrés a Badges-alapú szabályt használja (lásd:
    hierarchy._has_badge_descendant) - UGYANAZ a szabály, mint a
    collect_unique_assemblies-nél. Ha None, a régi (legalább N db
    alkatrészből álló összeállítás) heurisztika marad érvényben.
    """
    modules = []
    for node in root.children:
        if badge_keys is not None:
            if not _has_badge_descendant(node, badge_keys):
                continue
        else:
            if node.has_geometry:
                continue
            if not _has_panel_descendant(node):
                continue
            if _count_geometry_descendants(node) < MIN_PARTS_FOR_ASSEMBLY:
                continue
        bbox = subtree_world_bbox(node)
        if bbox is None:
            continue
        modules.append((node, bbox))
    return modules


def _render_layout_view(msp, modules, u_axis, v_axis, v_offset=0.0):
    """
    Egy nézet (pl. felülnézet vagy elölnézet) kirajzolása: minden modul
    saját téglalapja a VALÓS, egymáshoz képesti világpozíciójában és
    névvel, PLUSZ a modulhatárok (hol kezdődik/végződik egy-egy elem)
    lánc-méretvonala az u tengely mentén, és az egész elrendezés
    össz-mérete. `v_offset`-tel lehet lejjebb/feljebb tolni a teljes
    nézetet a lapon (pl. hogy egy második nézet alá kerüljön, ne
    fedjék egymást).

    Visszaadja: (u0, alsó_v_határ, u1, felső_v_határ) - a nézet által
    ténylegesen elfoglalt terület, a méretvonalakkal és a helynek
    szánt felirat-sávval együtt.
    """
    boxes = []
    for node, (mins, maxs) in modules:
        u0 = mins[u_axis]
        v0 = mins[v_axis] + v_offset
        width = maxs[u_axis] - mins[u_axis]
        height = maxs[v_axis] - mins[v_axis]
        boxes.append((node, u0, v0, width, height))

    for node, u0, v0, width, height in boxes:
        points = [
            (u0, v0), (u0 + width, v0),
            (u0 + width, v0 + height), (u0, v0 + height),
        ]
        msp.add_lwpolyline(points, close=True)
        msp.add_text(
            node.name, dxfattribs={"height": MODULE_LABEL_HEIGHT_MM},
        ).set_placement((u0 + 15, v0 + 15))

    all_u0 = min(b[1] for b in boxes)
    all_v0 = min(b[2] for b in boxes)
    all_u1 = max(b[1] + b[3] for b in boxes)
    all_v1 = max(b[2] + b[4] for b in boxes)

    u_edges = sorted({b[1] for b in boxes} | {b[1] + b[3] for b in boxes})
    chain = chain_dimensions(u_edges, "horizontal", fixed=all_v0, offset=LAYOUT_CHAIN_OFFSET_MM)
    _render_dimension_lines(msp, chain)

    overall = rectangle_dimensions(
        all_u0, all_v0, all_u1 - all_u0, all_v1 - all_v0, offset=LAYOUT_OVERALL_OFFSET_MM,
    )
    _render_dimension_lines(msp, overall)

    bottom = all_v0 - LAYOUT_OVERALL_OFFSET_MM - MODULE_LABEL_HEIGHT_MM * 4
    return all_u0, bottom, all_u1, all_v1


def export_layout(root, path, label="Konyha elrendezes (felulnezet)", badge_keys=None):
    """
    A teljes konyha alaprajza (felülnézet, VILÁG X-Z sík): minden
    közvetlen gyerek-modul saját lábnyomat-téglalapja a tényleges
    világpozícióban - így látszik, melyik modul hol áll a másikhoz
    képest -, névvel, a modulhatárok lánc-méretvonalával, és az egész
    elrendezés össz-méretével.

    `badge_keys`: lásd _collect_layout_modules.
    """
    doc = ezdxf.new(setup=True)
    _ensure_dimstyle(doc)
    msp = doc.modelspace()

    modules = _collect_layout_modules(root, badge_keys)
    if not modules:
        raise ValueError("Nincs egyetlen geometriával rendelkező modul sem.")

    u0, bottom, u1, v1 = _render_layout_view(msp, modules, u_axis=0, v_axis=2)

    msp.add_text(
        label, dxfattribs={"height": 200.0},
    ).set_placement((u0, v1 + 400.0))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))


def export_front_layout(root, path, label="Konyha elrendezes (elolnezet)", badge_keys=None):
    """
    A teljes konyha ELÖLNÉZETE (VILÁG X-Y sík): ugyanaz, mint az
    export_layout, csak szemből - hogyan állnak egymás mellett a
    szekrények, ha a konyhára ránézünk.

    `badge_keys`: lásd _collect_layout_modules.
    """
    doc = ezdxf.new(setup=True)
    _ensure_dimstyle(doc)
    msp = doc.modelspace()

    modules = _collect_layout_modules(root, badge_keys)
    if not modules:
        raise ValueError("Nincs egyetlen geometriával rendelkező modul sem.")

    u0, bottom, u1, v1 = _render_layout_view(msp, modules, u_axis=0, v_axis=1)

    msp.add_text(
        label, dxfattribs={"height": 200.0},
    ).set_placement((u0, v1 + 400.0))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))


def _render_full_layout_view(msp, view_label, vdata, view_specs, modules, y_offset=0.0, scale=1.0):
    """
    Egy nézet (felülnézet/oldalnézet/elölnézet) kirajzolása a teljes
    bútorzat áttekintő rajzán: a panelek/hardver rejtett-vonalas
    szerkezete, a szekrény-elemenkénti külső méretvonalak, és az egész
    elrendezés össz-mérete. `y_offset`-tel eltolható függőlegesen (több
    nézet egy lapon való egymás alá helyezéséhez - lásd:
    export_full_layout); egyetlen, önálló nézethez (lásd:
    export_full_layout_view) y_offset=0.0 marad. `scale` (lásd
    _text_scale_for_extent) a méretvonal-eltolásokat és a felirat-magasságot
    nagyítja fel a nézet tényleges méretéhez igazítva.

    Visszaadja a nézet alján lévő felirat y-koordinátáját (bottom).
    """
    chain_offset = LAYOUT_CHAIN_OFFSET_MM * scale
    overall_offset = LAYOUT_OVERALL_OFFSET_MM * scale
    label_height = MODULE_LABEL_HEIGHT_MM * scale

    rects = vdata["rects"]
    hardware = vdata["hardware"]
    view = vdata["view"]
    u0, v0 = vdata["origin"]
    u_axis, v_axis = view_specs[view_label][0], view_specs[view_label][1]

    segments = compute_visible_segments(rects)
    _add_segments(msp, segments, x_offset=0.0, y_offset=y_offset)
    _add_hardware_polygons(msp, hardware, x_offset=0.0, y_offset=y_offset)

    # Minden szekrény-elem SAJÁT külső méretvonala (szélesség +
    # magasság ezen a nézeten), a modul TÉNYLEGES befoglaló doboza
    # alapján - nem az alkatrészek/panelek szintjén.
    #
    # FONTOS: a SZÉLESSÉG méretvonalát egy KÖZÖS, a teljes nézet ALJÁN
    # futó vonalra tesszük (fixed=y_offset), NEM az adott modul saját
    # (esetenként eltérő mélységű/pozíciójú) alsó élére - különben a
    # méretvonal (és a hozzá tartozó segédvonal) a rajz KÖZEPÉN, más
    # modulok/vasalatok fölött futna végig, és olvashatatlanná tenné a
    # rajzot. A MAGASSÁG méretvonalát viszont - mivel az valóban a
    # modul saját függőleges kiterjedése - a modul saját bal szélén
    # hagyjuk, a szélesség-sorral nem ütközik (más "tengelyen" fut).
    width_dim_y = y_offset - chain_offset
    for _, (m_mins, m_maxs) in modules:
        box_u0 = m_mins[u_axis] - u0
        box_v0 = m_mins[v_axis] - v0 + y_offset
        box_width = m_maxs[u_axis] - m_mins[u_axis]
        box_height = m_maxs[v_axis] - m_mins[v_axis]

        width_dim = DimensionLine(
            kind="horizontal",
            p1=(box_u0, box_v0), p2=(box_u0 + box_width, box_v0),
            base=(box_u0, width_dim_y), value=box_width,
        )
        height_dim = DimensionLine(
            kind="vertical",
            p1=(box_u0, box_v0), p2=(box_u0, box_v0 + box_height),
            base=(box_u0 - chain_offset, box_v0), value=box_height,
        )
        _render_dimension_lines(msp, [width_dim, height_dim])

    overall = rectangle_dimensions(0.0, y_offset, view.width, view.height, offset=overall_offset)
    _render_dimension_lines(msp, overall)

    bottom = y_offset - overall_offset - label_height * 4
    msp.add_text(
        view_label, dxfattribs={"height": label_height},
    ).set_placement((0.0, bottom))

    return bottom


def _full_layout_render_data(root, badge_keys=None):
    """
    Közös előkészítő lépés export_full_layout és export_full_layout_view
    számára: a modulok, tengelyek és a mindhárom nézethez tartozó
    vetített geometria. Hibát dob, ha nincs mit rajzolni.
    """
    modules = _collect_layout_modules(root, badge_keys)
    if not modules:
        raise ValueError("Nincs egyetlen geometriával rendelkező modul sem.")

    axes = layout_axes(root)
    view_specs = layout_view_specs(axes)
    views_data = full_layout_views(modules, axes)
    if views_data is None:
        raise ValueError("Nincs egyetlen panel-elem sem a modulokban.")

    return modules, view_specs, views_data


def export_full_layout(root, path, label="Konyha elrendezes - attekinto rajz", badge_keys=None):
    """
    A teljes bútorzat áttekintő rajza EGY lapon, HÁROM nézettel
    (felülnézet, oldalnézet, elölnézet), egymás alatt: minden modul
    TELJES panel-szerkezete látszik (nem csak egy befoglaló téglalap),
    a LÁTHATÓ élek folytonos, a KÖZELEBBI elemek (akár egy másik modul
    is!) által ELTAKART élek szaggatott vonallal - ugyanaz a
    rajzolásmód, mint egyetlen bútorelem szerkezeti rajzánál
    (export_construction_views), csak az ÖSSZES modulra együtt, a
    valódi, egymáshoz képesti világpozícióban.

    Az apró (mindhárom oldalon 10cm alatti) alkatrészek/hardver-elemek
    NEM jelennek meg ezen a rajzon - lásd
    skp2draw.geometry.projection.full_layout_views /
    _is_negligible_size -, hogy ne zsúfolják tele az áttekintőt olyan
    részletekkel (dűbelek, apró kötőelemek), amik ezen a léptéken úgysem
    olvashatók.

    A méretezés MODULONKÉNT (szekrény-elemenként) a modul SAJÁT külső
    szélessége + magassága (nem az alkatrészek/panelek szintjén), PLUSZ
    az egész elrendezés össz-mérete nézetenként.

    `badge_keys`: lásd _collect_layout_modules.
    """
    modules, view_specs, views_data = _full_layout_render_data(root, badge_keys)
    overall_extent = max(
        max(vdata["view"].width, vdata["view"].height) for vdata in views_data.values()
    )
    scale = _text_scale_for_extent(overall_extent)
    title_height = TITLE_HEIGHT_MM * scale

    doc = ezdxf.new(setup=True)
    _ensure_dimstyle(doc, scale=scale)
    msp = doc.modelspace()

    # A nézeteket egymás ALÁ rakjuk a lapon. Mivel egy nézet (pl. az
    # elölnézet) sokkal magasabb lehet, mint amennyit egy fix távolsággal
    # elő tudnánk jósolni (magas szekrénysor esetén akár 2000+ mm), előbb
    # mindig a KÖVETKEZŐ nézet SAJÁT magasságát vesszük figyelembe, hogy
    # sose csússzon egybe az előzővel.
    prev_bottom = None
    first_top = None

    for view_label in ("felülnézet", "oldalnézet", "elölnézet"):
        vdata = views_data[view_label]
        view = vdata["view"]

        y_offset = 0.0 if prev_bottom is None else prev_bottom - LAYOUT_VIEW_GAP_MM - view.height
        if prev_bottom is None:
            first_top = view.height

        bottom = _render_full_layout_view(
            msp, view_label, vdata, view_specs, modules, y_offset=y_offset, scale=scale,
        )
        prev_bottom = bottom

    msp.add_text(
        label, dxfattribs={"height": title_height},
    ).set_placement((0.0, first_top + title_height * 3))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))


def export_full_layout_view(root, view_label: str, path, label: str | None = None, badge_keys=None):
    """
    A teljes bútorzat áttekintő rajzának EGYETLEN nézete (`view_label`:
    "felülnézet", "oldalnézet" vagy "elölnézet") KÜLÖN DXF lapon -
    ugyanaz a rajzolásmód, mint export_full_layout-nál, csak
    nézetenként külön fájlban (pl. a PDF-generáláshoz, ahol az áttekintő
    mindhárom nézete külön oldalra kerül).

    `badge_keys`: lásd _collect_layout_modules.
    """
    modules, view_specs, views_data = _full_layout_render_data(root, badge_keys)
    if view_label not in views_data:
        raise ValueError(f"Ismeretlen nézet: {view_label!r}")

    vdata = views_data[view_label]
    overall_extent = max(vdata["view"].width, vdata["view"].height)
    scale = _text_scale_for_extent(overall_extent)
    title_height = TITLE_HEIGHT_MM * scale

    doc = ezdxf.new(setup=True)
    _ensure_dimstyle(doc, scale=scale)
    msp = doc.modelspace()

    _render_full_layout_view(msp, view_label, vdata, view_specs, modules, y_offset=0.0, scale=scale)

    title = label or f"Konyha elrendezes - attekinto rajz ({view_label})"
    msp.add_text(
        title, dxfattribs={"height": title_height},
    ).set_placement((0.0, vdata["view"].height + title_height * 3))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))


def _add_segments(msp, segments, x_offset=0.0, y_offset=0.0):
    for seg in segments:
        linetype = "Continuous" if seg.visible else "DASHED"
        msp.add_line(
            (seg.u0 + x_offset, seg.v0 + y_offset),
            (seg.u1 + x_offset, seg.v1 + y_offset),
            dxfattribs={"linetype": linetype},
        )

CHAIN_OFFSET_MM = 15.0      # a részlet-lánc távolsága a rajztól
OVERALL_OFFSET_MM = 45.0    # az össz-méret távolsága a rajztól (a lánc UTÁN)
MAJOR_PANEL_MIN_MM = 100.0  # ennél kisebb (bármelyik irányban) elemek NEM
                             # kapnak saját méretvonalat a láncban (pl. kis
                             # sarok-csatlakozók) - a RAJZON továbbra is
                             # megjelennek, csak nem méretezzük őket külön

def export_construction_views(node, label: str, path, count: int = 1, views_data=None):
    """
    Egy összeállítás (bútorelem) három nézete (elölnézet, felülnézet,
    oldalnézet), MINDEN panel-alkotóelem körvonalával: a LÁTHATÓ élek
    folytonos, a KÖZELEBBI alkatrészek által ELTAKART élek szaggatott
    vonallal. A "fő" (min. 100mm-es) alkatrész-határokhoz méretvonal
    tartozik: egy közeli "részlet-lánc" az egyes szakaszokra, plusz egy
    távolabbi méretvonal az össz-méretre.
    """


    if views_data is None:
        views_data = assembly_construction_views(node)
    if views_data is None:
        raise ValueError(f"Nincs geometria: {label}")

    overall_extent = max(
        max(views_data[lbl]["view"].width, views_data[lbl]["view"].height)
        for lbl in ("elölnézet", "felülnézet", "oldalnézet")
    )
    scale = _text_scale_for_extent(overall_extent)

    # A szöveg mérete ÉS a köréje szánt hely (segédvonal-eltolás, rés a
    # nézetek között) is `scale`-lel nő - különben egy nagyobb bútorelemnél
    # a megnövelt szöveg belelógna a fölötte/alatta lévő méretvonalba.
    chain_offset = CHAIN_OFFSET_MM * scale
    overall_offset = OVERALL_OFFSET_MM * scale
    gap = GAP_MM * scale
    label_height = LABEL_HEIGHT_MM * scale
    title_height = TITLE_HEIGHT_MM * scale

    doc = ezdxf.new(setup=True)
    _ensure_dimstyle(doc, scale=scale)
    msp = doc.modelspace()

    # A három nézet EGYMÁS ALATT kerül a lapra (nem egymás mellett) - így
    # egy A4 álló oldalon nagyobbra vehető mindegyik. `floor`: lásd
    # export_views - a KÖVETKEZŐ nézet origóját a SAJÁT magasságával
    # együtt kell az eddig felhasznált terület alá helyezni, különben egy
    # magasabb nézet átfedésbe kerülne egy előtte lévő, alacsonyabbal.
    floor = None
    title_top = None
    for view_label in ("elölnézet", "felülnézet", "oldalnézet"):
        v = views_data[view_label]["view"]
        y_cursor = 0.0 if floor is None else floor - gap - v.height
        rects = views_data[view_label]["rects"]
        segments = compute_visible_segments(rects)
        _add_segments(msp, segments, x_offset=0.0, y_offset=y_cursor)
        _add_hardware_polygons(msp, views_data[view_label]["hardware"], x_offset=0.0, y_offset=y_cursor)

        major_rects = [
            r for r in rects
            if (r.u1 - r.u0) >= MAJOR_PANEL_MIN_MM and (r.v1 - r.v0) >= MAJOR_PANEL_MIN_MM
        ]
        u_coords = [r.u0 for r in major_rects] + [r.u1 for r in major_rects]
        v_coords_local = [r.v0 for r in major_rects] + [r.v1 for r in major_rects]
        u_coords += [0.0, v.width]
        v_coords_local += [0.0, v.height]
        v_coords_world = [c + y_cursor for c in v_coords_local]

        horiz_chain = chain_dimensions(
            u_coords, "horizontal",
            fixed=y_cursor, offset=chain_offset,
        )
        vert_chain = chain_dimensions(
            v_coords_world, "vertical",
            fixed=0.0, offset=chain_offset,
        )
        _render_dimension_lines(msp, horiz_chain)
        _render_dimension_lines(msp, vert_chain)

        overall = rectangle_dimensions(0.0, y_cursor, v.width, v.height, offset=overall_offset)
        _render_dimension_lines(msp, overall)

        label_y = y_cursor - overall_offset - label_height * 3
        msp.add_text(
            v.label,
            dxfattribs={"height": label_height},
        ).set_placement((0.0, label_y))

        if title_top is None:
            title_top = y_cursor + v.height
        floor = label_y - label_height

    title = label if count == 1 else f"{label}  ({count} db)"
    msp.add_text(
        title,
        dxfattribs={"height": title_height},
    ).set_placement((0.0, title_top + overall_offset + title_height * 3))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))