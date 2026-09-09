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
from skp2draw.geometry.projection import assembly_construction_views
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


def _add_rectangle(msp, x0, y0, width, height):
    points = [
        (x0, y0), (x0 + width, y0),
        (x0 + width, y0 + height), (x0, y0 + height),
    ]
    msp.add_lwpolyline(points, close=True)


def _add_dimensions(msp, x0, y0, width, height):
    for dim in rectangle_dimensions(x0, y0, width, height, offset=DIM_OFFSET_MM):
        angle = 0 if dim.kind == "horizontal" else 90
        dxf_dim = msp.add_linear_dim(
            base=dim.base, p1=dim.p1, p2=dim.p2, angle=angle,
            dimstyle=DIMSTYLE_NAME,
        )
        dxf_dim.render()

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


def export_layout(root, path, label="Konyha elrendezes (felulnezet)"):
    """
    A teljes konyha alaprajza (felülnézet): minden közvetlen gyerek-modul
    közül a VALÓDI ÖSSZEÁLLÍTÁSOK (nem egyetlen panel, nem csak hardware-
    konténer) saját lábnyomat-téglalapja a VILÁG X-Z síkjában, a tényleges
    világpozícióban - így látszik, melyik modul hol áll a másikhoz képest.
    Plusz az egész elrendezés befoglaló méretei (teljes szélesség/mélység).
    """
    doc = ezdxf.new(setup=True)
    _ensure_dimstyle(doc)
    msp = doc.modelspace()

    module_boxes = []
    for node in root.children:
        if node.has_geometry:
            continue  # ez maga egy alkatrész (pl. önálló panel), nem összeállítás
        if not _has_panel_descendant(node):
            continue  # pl. csak hardware-t tartalmazó konténer
        if _count_geometry_descendants(node) < MIN_PARTS_FOR_ASSEMBLY:
            continue  # egyetlen panelt csomagoló konténer (pl. egy önálló ajtó)

        bbox = subtree_world_bbox(node)
        if bbox is None:
            continue
        mins, maxs = bbox
        x0, z0 = mins[0], mins[2]
        width, depth = maxs[0] - mins[0], maxs[2] - mins[2]
        module_boxes.append((node, x0, z0, width, depth))

    if not module_boxes:
        raise ValueError("Nincs egyetlen geometriával rendelkező modul sem.")

    for node, x0, z0, width, depth in module_boxes:
        points = [
            (x0, z0), (x0 + width, z0),
            (x0 + width, z0 + depth), (x0, z0 + depth),
        ]
        msp.add_lwpolyline(points, close=True)
        msp.add_text(
            node.name, dxfattribs={"height": 40.0},
        ).set_placement((x0 + 15, z0 + 15))

    all_x0 = min(b[1] for b in module_boxes)
    all_z0 = min(b[2] for b in module_boxes)
    all_x1 = max(b[1] + b[3] for b in module_boxes)
    all_z1 = max(b[2] + b[4] for b in module_boxes)

    for dim in rectangle_dimensions(all_x0, all_z0, all_x1 - all_x0, all_z1 - all_z0, offset=150.0):
        angle = 0 if dim.kind == "horizontal" else 90
        dxf_dim = msp.add_linear_dim(
            base=dim.base, p1=dim.p1, p2=dim.p2, angle=angle,
            dimstyle=DIMSTYLE_NAME,
        )
        dxf_dim.render()

    msp.add_text(
        label, dxfattribs={"height": 200.0},
    ).set_placement((all_x0, all_z1 + 400.0))

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


def _render_dimension_lines(msp, dims):
    for dim in dims:
        angle = 0 if dim.kind == "horizontal" else 90
        dxf_dim = msp.add_linear_dim(
            base=dim.base, p1=dim.p1, p2=dim.p2, angle=angle,
            dimstyle=DIMSTYLE_NAME,
        )
        dxf_dim.render()


def export_construction_views(node, label: str, path, count: int = 1):
    """
    Egy összeállítás (bútorelem) három nézete (elölnézet, felülnézet,
    oldalnézet), MINDEN panel-alkotóelem körvonalával: a LÁTHATÓ élek
    folytonos, a KÖZELEBBI alkatrészek által ELTAKART élek szaggatott
    vonallal. A "fő" (min. 100mm-es) alkatrész-határokhoz méretvonal
    tartozik: egy közeli "részlet-lánc" az egyes szakaszokra, plusz egy
    távolabbi méretvonal az össz-méretre.
    """
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