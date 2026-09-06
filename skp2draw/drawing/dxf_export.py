"""
Egy panel-komponens három nézetének (elölnézet, felülnézet, oldalnézet)
DXF rajzzá alakítása: téglalapok, VALÓDI méretvonalakkal (nyilakkal és
felirattal), ahogy egy tényleges műszaki rajzon. Emellett a teljes
konyha elrendezés-rajzának (alaprajz) exportja is itt van.
"""
from __future__ import annotations
from pathlib import Path
import ezdxf

from skp2draw.dimensioning.rules import rectangle_dimensions
from skp2draw.geometry.bbox import subtree_world_bbox
from skp2draw.hierarchy import _has_panel_descendant, _count_geometry_descendants, MIN_PARTS_FOR_ASSEMBLY

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