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
from skp2draw.hierarchy import _has_panel_descendant, _count_geometry_descendants, MIN_PARTS_FOR_ASSEMBLY
from skp2draw.geometry.projection import assembly_construction_views, layout_axes, layout_view_specs, full_layout_views
from skp2draw.geometry.hidden_line import compute_visible_segments
from skp2draw.dimensioning.rules import rectangle_dimensions, chain_dimensions

GAP_MM = 60.0
TITLE_HEIGHT_MM = 12.0
LABEL_HEIGHT_MM = 8.0
DIM_OFFSET_MM = 15.0

DIMSTYLE_NAME = "MUSZAKI"


def _ensure_dimstyle(doc):
    """
    Az ezdxf alapértelmezett méretstílusa (dimtxt=0.25, dimasz=0.175) egy
    "egységnyi" rajzhoz van hangolva - nálunk viszont a rajzi egység = 1 mm,
    és a modell többszáz mm, szóval saját, a rajz méretéhez illő stílust
    definiálunk (mm-es szöveg- és nyílméretekkel).
    """
    if DIMSTYLE_NAME in doc.dimstyles:
        return
    style = doc.dimstyles.new(DIMSTYLE_NAME)
    style.dxf.dimtxt = 10.0   # szöveg magassága, mm
    style.dxf.dimasz = 8.0    # nyílvégződés mérete, mm
    style.dxf.dimexe = 5.0    # segédvonal túlnyúlása a méretvonalon
    style.dxf.dimexo = 3.0    # segédvonal távolsága a mért ponttól
    style.dxf.dimgap = 2.0    # rés a méretvonal és a szöveg között

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


def export_views(views, label: str, path, count: int = 1):
    doc = ezdxf.new(setup=True)
    _ensure_dimstyle(doc)
    msp = doc.modelspace()

    x_cursor = 0.0
    max_top = 0.0
    for v in views:
        _add_rectangle(msp, x_cursor, 0.0, v.width, v.height)
        _add_dimensions(msp, x_cursor, 0.0, v.width, v.height)

        msp.add_text(
            v.label,
            dxfattribs={"height": LABEL_HEIGHT_MM},
        ).set_placement((x_cursor, -DIM_OFFSET_MM - LABEL_HEIGHT_MM * 4))

        max_top = max(max_top, v.height)
        x_cursor += v.width + GAP_MM

    title = label if count == 1 else f"{label}  ({count} db)"
    msp.add_text(
        title,
        dxfattribs={"height": TITLE_HEIGHT_MM},
    ).set_placement((0.0, max_top + DIM_OFFSET_MM + TITLE_HEIGHT_MM * 3))

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
MODULE_LABEL_HEIGHT_MM = 30.0


def _collect_layout_modules(root):
    """
    A root közvetlen gyerekei közül a VALÓDI ÖSSZEÁLLÍTÁSOKAT gyűjti össze
    (ugyanaz a szűrés, mint collect_unique_assemblies-nál: nincs saját
    geometriája, van legalább egy panel-leszármazottja, és legalább
    MIN_PARTS_FOR_ASSEMBLY db geometriával rendelkező leszármazottja),
    a VILÁG-koordinátás befoglaló dobozukkal (mins, maxs) együtt - ez
    adja meg minden modul TÉNYLEGES, egymáshoz képesti helyzetét.
    """
    modules = []
    for node in root.children:
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


def export_layout(root, path, label="Konyha elrendezes (felulnezet)"):
    """
    A teljes konyha alaprajza (felülnézet, VILÁG X-Z sík): minden közvetlen
    gyerek-modul (VALÓDI ÖSSZEÁLLÍTÁS) saját lábnyomat-téglalapja a
    tényleges világpozícióban - így látszik, melyik modul hol áll a
    másikhoz képest -, névvel, a modulhatárok lánc-méretvonalával, és
    az egész elrendezés össz-méretével.
    """
    doc = ezdxf.new(setup=True)
    _ensure_dimstyle(doc)
    msp = doc.modelspace()

    modules = _collect_layout_modules(root)
    if not modules:
        raise ValueError("Nincs egyetlen geometriával rendelkező modul sem.")

    u0, bottom, u1, v1 = _render_layout_view(msp, modules, u_axis=0, v_axis=2)

    msp.add_text(
        label, dxfattribs={"height": 200.0},
    ).set_placement((u0, v1 + 400.0))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))


def export_front_layout(root, path, label="Konyha elrendezes (elolnezet)"):
    """
    A teljes konyha ELÖLNÉZETE (VILÁG X-Y sík): ugyanaz, mint az
    export_layout, csak szemből - hogyan állnak egymás mellett a
    szekrények, ha a konyhára ránézünk.
    """
    doc = ezdxf.new(setup=True)
    _ensure_dimstyle(doc)
    msp = doc.modelspace()

    modules = _collect_layout_modules(root)
    if not modules:
        raise ValueError("Nincs egyetlen geometriával rendelkező modul sem.")

    u0, bottom, u1, v1 = _render_layout_view(msp, modules, u_axis=0, v_axis=1)

    msp.add_text(
        label, dxfattribs={"height": 200.0},
    ).set_placement((u0, v1 + 400.0))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))


def export_full_layout(root, path, label="Konyha elrendezes - attekinto rajz"):
    """
    A teljes bútorzat áttekintő rajza EGY lapon, HÁROM nézettel
    (felülnézet, oldalnézet, elölnézet), egymás alatt: minden modul
    TELJES panel-szerkezete látszik (nem csak egy befoglaló téglalap),
    a LÁTHATÓ élek folytonos, a KÖZELEBBI elemek (akár egy másik modul
    is!) által ELTAKART élek szaggatott vonallal - ugyanaz a
    rajzolásmód, mint egyetlen bútorelem szerkezeti rajzánál
    (export_construction_views), csak az ÖSSZES modulra együtt, a
    valódi, egymáshoz képesti világpozícióban. Minden nézeten a
    modulhatárok lánc-méretvonala (hol kezdődik/végződik egy-egy elem)
    és az egész elrendezés össz-mérete is szerepel.
    """
    doc = ezdxf.new(setup=True)
    _ensure_dimstyle(doc)
    msp = doc.modelspace()

    modules = _collect_layout_modules(root)
    if not modules:
        raise ValueError("Nincs egyetlen geometriával rendelkező modul sem.")

    axes = layout_axes(root)
    view_specs = layout_view_specs(axes)
    views_data = full_layout_views(modules, axes)
    if views_data is None:
        raise ValueError("Nincs egyetlen panel-elem sem a modulokban.")

    # A nézeteket egymás ALÁ rakjuk a lapon. Mivel egy nézet (pl. az
    # elölnézet) sokkal magasabb lehet, mint amennyit egy fix távolsággal
    # elő tudnánk jósolni (magas szekrénysor esetén akár 2000+ mm), előbb
    # mindig a KÖVETKEZŐ nézet SAJÁT magasságát vesszük figyelembe, hogy
    # sose csússzon egybe az előzővel.
    prev_bottom = None
    first_top = None

    for view_label in ("felülnézet", "oldalnézet", "elölnézet"):
        vdata = views_data[view_label]
        rects = vdata["rects"]
        hardware = vdata["hardware"]
        view = vdata["view"]
        u0, _v0 = vdata["origin"]
        u_axis = view_specs[view_label][0]

        y_offset = 0.0 if prev_bottom is None else prev_bottom - LAYOUT_VIEW_GAP_MM - view.height
        if prev_bottom is None:
            first_top = view.height

        segments = compute_visible_segments(rects)
        _add_segments(msp, segments, x_offset=0.0, y_offset=y_offset)
        _add_hardware_polygons(msp, hardware, x_offset=0.0, y_offset=y_offset)

        # modulhatárok lánc-méretvonala: hol kezdődik/végződik egy-egy elem
        u_edges = sorted(
            {m_mins[u_axis] - u0 for _, (m_mins, m_maxs) in modules}
            | {m_maxs[u_axis] - u0 for _, (m_mins, m_maxs) in modules}
        )
        chain = chain_dimensions(u_edges, "horizontal", fixed=y_offset, offset=LAYOUT_CHAIN_OFFSET_MM)
        _render_dimension_lines(msp, chain)

        overall = rectangle_dimensions(0.0, y_offset, view.width, view.height, offset=LAYOUT_OVERALL_OFFSET_MM)
        _render_dimension_lines(msp, overall)

        bottom = y_offset - LAYOUT_OVERALL_OFFSET_MM - MODULE_LABEL_HEIGHT_MM * 4
        msp.add_text(
            view_label, dxfattribs={"height": MODULE_LABEL_HEIGHT_MM},
        ).set_placement((0.0, bottom))

        prev_bottom = bottom

    msp.add_text(
        label, dxfattribs={"height": 200.0},
    ).set_placement((0.0, first_top + 400.0))

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

    doc = ezdxf.new(setup=True)
    _ensure_dimstyle(doc)
    msp = doc.modelspace()

    x_cursor = 0.0
    max_top = 0.0
    for view_label in ("elölnézet", "felülnézet", "oldalnézet"):
        v = views_data[view_label]["view"]
        rects = views_data[view_label]["rects"]
        segments = compute_visible_segments(rects)
        _add_segments(msp, segments, x_offset=x_cursor, y_offset=0.0)
        _add_hardware_polygons(msp, views_data[view_label]["hardware"], x_offset=x_cursor, y_offset=0.0)

        major_rects = [
            r for r in rects
            if (r.u1 - r.u0) >= MAJOR_PANEL_MIN_MM and (r.v1 - r.v0) >= MAJOR_PANEL_MIN_MM
        ]
        u_coords = [r.u0 for r in major_rects] + [r.u1 for r in major_rects]
        v_coords = [r.v0 for r in major_rects] + [r.v1 for r in major_rects]
        u_coords += [0.0, v.width]
        v_coords += [0.0, v.height]

        horiz_chain = chain_dimensions(
            [c + x_cursor for c in u_coords], "horizontal",
            fixed=0.0, offset=CHAIN_OFFSET_MM,
        )
        vert_chain = chain_dimensions(
            v_coords, "vertical",
            fixed=x_cursor, offset=CHAIN_OFFSET_MM,
        )
        _render_dimension_lines(msp, horiz_chain)
        _render_dimension_lines(msp, vert_chain)

        overall = rectangle_dimensions(x_cursor, 0.0, v.width, v.height, offset=OVERALL_OFFSET_MM)
        _render_dimension_lines(msp, overall)

        msp.add_text(
            v.label,
            dxfattribs={"height": LABEL_HEIGHT_MM},
        ).set_placement((x_cursor, -OVERALL_OFFSET_MM - LABEL_HEIGHT_MM * 3))

        max_top = max(max_top, v.height)
        x_cursor += v.width + GAP_MM + OVERALL_OFFSET_MM

    title = label if count == 1 else f"{label}  ({count} db)"
    msp.add_text(
        title,
        dxfattribs={"height": TITLE_HEIGHT_MM},
    ).set_placement((0.0, max_top + OVERALL_OFFSET_MM + TITLE_HEIGHT_MM * 3))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))