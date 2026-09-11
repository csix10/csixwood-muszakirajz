"""
Panel-komponensek (sík bútorlapok) 2D vetítése műszaki nézetekhez, és
teljes összeállítások (bútorelemek, konyha-elrendezés) 3 alap nézete,
plusz a rejtett-vonalas ("szerkezeti") nézetekhez szükséges Rect-gyűjtés.
"""

from __future__ import annotations
from dataclasses import dataclass
import unicodedata
import numpy as np
from skp2draw.parser.model import Node
from skp2draw.geometry.bbox import scaled_local_sizes, subtree_bbox_in_frame, subtree_points_in_frame
from skp2draw.geometry.hidden_line import Rect, convex_hull_2d, point_in_rect
from skp2draw.hierarchy import classify_kind


@dataclass
class View:
    label: str
    width: float
    height: float


def panel_views(node: Node):
    sizes = scaled_local_sizes(node)
    if sizes is None:
        return None

    t_axis = int(np.argmin(sizes))
    plane_axes = [i for i in range(3) if i != t_axis]
    u_axis, v_axis = plane_axes
    thickness = sizes[t_axis]
    width = sizes[u_axis]
    height = sizes[v_axis]

    return [
        View(label="elölnézet", width=width, height=height),
        View(label="felülnézet", width=width, height=thickness),
        View(label="oldalnézet", width=height, height=thickness),
    ]


def _normalize(text: str) -> str:
    """Ékezetek levétele + kisbetűs, hogy 'Hátlap'/'hatlap' egyformán találjon."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text or "")
        if unicodedata.category(c) != "Mn"
    ).lower()


_BACK_PANEL_HINTS = ("hatlap", "hatfal")


def _find_back_panel(node: Node) -> Node | None:
    """
    Megkeresi a modul részfájában az első olyan panelt, aminek a nevében
    'hátlap' vagy 'hátfal' szerepel (ékezet-független). A hátlap mindig
    HÁTUL van egy bútordarabon, így a vastagság-tengelye megbízhatóan
    kijelöli a modul MÉLYSÉG irányát.
    """
    name_norm = _normalize(node.definition_name)
    if node.has_geometry and any(hint in name_norm for hint in _BACK_PANEL_HINTS):
        return node
    for c in node.children:
        found = _find_back_panel(c)
        if found is not None:
            return found
    return None


def _assembly_axes(node: Node, frame):
    """
    Meghatározza a modul SZÉLESSÉG / MAGASSÁG / MÉLYSÉG tengelyét (0/1/2
    indexek a frame-ben), plusz a MÉLYSÉG előjelét (melyik irányban van
    "előre", a néző felé).
    """
    bbox = subtree_bbox_in_frame(node, frame)
    mins, maxs = bbox
    sizes = maxs - mins
    center = (mins + maxs) / 2

    HEIGHT_AXIS = 1

    back_panel = _find_back_panel(node)
    depth_axis = None
    depth_sign = 1.0
    if back_panel is not None:
        back_bbox = subtree_bbox_in_frame(back_panel, frame)
        if back_bbox is not None:
            b_mins, b_maxs = back_bbox
            b_sizes = b_maxs - b_mins
            depth_axis = int(np.argmin(b_sizes))
            if depth_axis != HEIGHT_AXIS:
                back_center = (b_mins[depth_axis] + b_maxs[depth_axis]) / 2
                depth_sign = 1.0 if back_center > center[depth_axis] else -1.0

    if depth_axis is None or depth_axis == HEIGHT_AXIS:
        remaining = [i for i in range(3) if i != HEIGHT_AXIS]
        depth_axis = remaining[0] if sizes[remaining[0]] < sizes[remaining[1]] else remaining[1]
        depth_sign = 1.0

    width_axis = ({0, 1, 2} - {HEIGHT_AXIS, depth_axis}).pop()
    return width_axis, HEIGHT_AXIS, depth_axis, depth_sign


def assembly_views(node: Node, frame=None):
    """
    Egy teljes összeállítás három alap nézete: elölnézet (szélesség x
    magasság), felülnézet (szélesség x mélység), oldalnézet (mélység x
    magasság). CSAK a méreteket adja vissza (View-k listája), geometria
    nélkül - ez kell pl. a fájlnévhez.
    """
    frame = node.world_matrix if frame is None else frame
    bbox = subtree_bbox_in_frame(node, frame)
    if bbox is None:
        return None
    mins, maxs = bbox
    sizes = maxs - mins

    width_axis, height_axis, depth_axis, _ = _assembly_axes(node, frame)

    return [
        View(label="elölnézet", width=sizes[width_axis], height=sizes[height_axis]),
        View(label="felülnézet", width=sizes[width_axis], height=sizes[depth_axis]),
        View(label="oldalnézet", width=sizes[depth_axis], height=sizes[height_axis]),
    ]

def _collect_by_kind(node: Node, kind: str) -> list[Node]:
    """Az összes adott KIND-ként ('panel' vagy 'hardware') osztályozott leszármazott, bármilyen mélyen beágyazva."""
    result = []

    def walk(n: Node):
        if n.has_geometry and classify_kind(n) == kind:
            result.append(n)
        for c in n.children:
            walk(c)

    walk(node)
    return result

def assembly_construction_views(node: Node, frame=None):
    """
    Az összeállítás mindhárom nézetéhez (elölnézet, felülnézet, oldalnézet)
    visszaadja a View-t, az összes panel-leszármazott Rect-jét, ÉS az
    összes hardware-leszármazott (láb, pánt, lamello stb.) 2D konvex
    burkát - már a nézet saját (0,0) origójához igazítva.

    Visszaad: {"elölnézet": {"view": View, "rects": [...], "hardware": [...]}, ...}
    """
    frame = node.world_matrix if frame is None else frame
    bbox = subtree_bbox_in_frame(node, frame)
    if bbox is None:
        return None
    mins, maxs = bbox
    sizes = maxs - mins

    width_axis, height_axis, depth_axis, depth_sign = _assembly_axes(node, frame)

    view_specs = {
        "elölnézet": (width_axis, height_axis, depth_axis, depth_sign),
        "felülnézet": (width_axis, depth_axis, height_axis, -1.0),
        "oldalnézet": (depth_axis, height_axis, width_axis, 1.0),
    }

    panels = _collect_by_kind(node, "panel")
    panel_bboxes = [(p, subtree_bbox_in_frame(p, frame)) for p in panels]
    panel_bboxes = [(p, b) for p, b in panel_bboxes if b is not None]

    hardware = _collect_by_kind(node, "hardware")
    hardware_points = [(h, subtree_points_in_frame(h, frame)) for h in hardware]
    hardware_points = [(h, p) for h, p in hardware_points if p is not None]

    result = {}
    for label, (u_axis, v_axis, dist_axis, dist_sign) in view_specs.items():
        u0, v0 = mins[u_axis], mins[v_axis]

        rects = []
        for panel, (pmins, pmaxs) in panel_bboxes:
            near = min(dist_sign * pmins[dist_axis], dist_sign * pmaxs[dist_axis])
            rects.append(Rect(
                u0=pmins[u_axis] - u0, v0=pmins[v_axis] - v0,
                u1=pmaxs[u_axis] - u0, v1=pmaxs[v_axis] - v0,
                distance=near, label=panel.name or panel.definition_name,
            ))

        hardware_polys = []
        for hw, pts in hardware_points:
            proj = [(float(p[u_axis]) - u0, float(p[v_axis]) - v0) for p in pts]
            hull = convex_hull_2d(proj)
            if len(hull) < 3:
                continue
            distance = float((pts[:, dist_axis] * dist_sign).min())
            cu = sum(p[0] for p in hull) / len(hull)
            cv = sum(p[1] for p in hull) / len(hull)
            closer = [r for r in rects if r.distance < distance]
            visible = not any(point_in_rect(cu, cv, r) for r in closer)
            hardware_polys.append({
                "points": hull, "visible": visible,
                "label": hw.name or hw.definition_name,
            })

        view = View(label=label, width=sizes[u_axis], height=sizes[v_axis])
        result[label] = {"view": view, "rects": rects, "hardware": hardware_polys}

    return result


# ---- Teljes bútorzat (több modul EGYÜTT) nézetei ----
#
# Az assembly_construction_views EGYETLEN modult néz, a SAJÁT (world_matrix
# szerinti) keretében, és a nézet (0,0) origóját mindig az adott modul
# saját bbox-ának bal-alsó sarkára tolja. Ha ezt egyenként hívnánk meg
# minden modulra, minden modul a saját (0,0)-ban landolna - elveszne az
# egymáshoz képesti VALÓDI pozíciójuk, pont az, amit a "teljes bútorzat"
# rajznak be kellene mutatnia. Ezért itt EGYSÉGES (globális, a teljes
# gyökérre meghatározott) tengelyeket használunk, és a panelek/hardver
# VILÁG-koordinátáit csak egyetlen, KÖZÖS (u0, v0) eltolással toljuk a
# rajzlap origójához - a modulok egymáshoz képesti helyzete megmarad.


def layout_axes(root: Node, frame=None):
    """
    A TELJES bútorzat SZÉLESSÉG / MAGASSÁG / MÉLYSÉG tengelye - ugyanaz a
    logika, mint egyetlen összeállításnál (_assembly_axes), csak a
    gyökérre alkalmazva, hogy a teljes elrendezés-rajz mindhárom nézete
    (felül-, oldal-, elölnézet) egységes tengelyeket használjon minden
    modulnál, függetlenül attól, hogy melyik modult nézzük éppen.
    """
    frame = np.eye(4) if frame is None else frame
    return _assembly_axes(root, frame)


def layout_view_specs(axes):
    """
    A TELJES bútorzat mindhárom nézetéhez tartozó (u_axis, v_axis,
    dist_axis, dist_sign) tengely-hozzárendelés a layout_axes(root)
    eredménye (width_axis, height_axis, depth_axis, depth_sign) alapján -
    ugyanaz a leképezés, mint assembly_construction_views-nál, csak
    nyilvánosan is elérhető, hogy a rajzoló réteg (dxf_export) a
    modulhatárok elhelyezéséhez fel tudja használni ugyanazokat a
    tengelyeket, amikkel a panel-geometria készült.
    """
    width_axis, height_axis, depth_axis, depth_sign = axes
    return {
        "elölnézet": (width_axis, height_axis, depth_axis, depth_sign),
        "felülnézet": (width_axis, depth_axis, height_axis, -1.0),
        "oldalnézet": (depth_axis, height_axis, width_axis, 1.0),
    }


def full_layout_views(modules, axes, frame=None):
    """
    A teljes bútorzat (TÖBB modul EGYÜTT) mindhárom nézete: minden modul
    ÖSSZES panel- és hardver-leszármazottjának Rect/hull adata, a modulok
    egymáshoz képesti VALÓDI világpozíciójában (nem az egyes modulok
    saját (0,0) origójára tolva) - így az összes panel EGYÜTT megy át a
    rejtett-vonal (occlusion) számításon: egy modul eltakarhatja a
    mögötte/alatta lévő másik modul éleit is, nem csak a saját belső
    paneleket.

    `modules`: (Node, (mins, maxs)) párok listája, lásd:
    dxf_export._collect_layout_modules. `axes`: (width_axis, height_axis,
    depth_axis, depth_sign), pl. layout_axes(root) eredménye.

    Visszaad: {"elölnézet": {"view": View, "rects": [...],
    "hardware": [...], "origin": (u0, v0)}, ...} - ugyanabban a
    formában, mint assembly_construction_views, plusz az "origin": ez az
    a (u0, v0) világ-eltolás, amivel a rects/hardware már el van tolva
    a nézet (0,0) origójához - a hívónak (pl. a modulhatár-
    méretvonalakhoz) ugyanezt kell levonnia a modulok saját bbox-ából.
    Ha egyetlen modulban sincs panel, None-t ad vissza.
    """
    frame = np.eye(4) if frame is None else frame
    view_specs = layout_view_specs(axes)

    panel_data = []
    hardware_data = []
    for node, _ in modules:
        for panel in _collect_by_kind(node, "panel"):
            bbox = subtree_bbox_in_frame(panel, frame)
            if bbox is not None:
                panel_data.append((panel, bbox[0], bbox[1]))
        for hw in _collect_by_kind(node, "hardware"):
            pts = subtree_points_in_frame(hw, frame)
            if pts is not None:
                hardware_data.append((hw, pts))

    if not panel_data:
        return None

    all_mins = np.array([mins for _, (mins, maxs) in modules]).min(axis=0)
    all_maxs = np.array([maxs for _, (mins, maxs) in modules]).max(axis=0)

    result = {}
    for label, (u_axis, v_axis, dist_axis, dist_sign) in view_specs.items():
        u0, v0 = all_mins[u_axis], all_mins[v_axis]

        rects = []
        for panel, pmins, pmaxs in panel_data:
            near = min(dist_sign * pmins[dist_axis], dist_sign * pmaxs[dist_axis])
            rects.append(Rect(
                u0=pmins[u_axis] - u0, v0=pmins[v_axis] - v0,
                u1=pmaxs[u_axis] - u0, v1=pmaxs[v_axis] - v0,
                distance=near, label=panel.name or panel.definition_name,
            ))

        hardware_polys = []
        for hw, pts in hardware_data:
            proj = [(float(p[u_axis]) - u0, float(p[v_axis]) - v0) for p in pts]
            hull = convex_hull_2d(proj)
            if len(hull) < 3:
                continue
            distance = float((pts[:, dist_axis] * dist_sign).min())
            cu = sum(p[0] for p in hull) / len(hull)
            cv = sum(p[1] for p in hull) / len(hull)
            closer = [r for r in rects if r.distance < distance]
            visible = not any(point_in_rect(cu, cv, r) for r in closer)
            hardware_polys.append({
                "points": hull, "visible": visible,
                "label": hw.name or hw.definition_name,
            })

        width = all_maxs[u_axis] - all_mins[u_axis]
        height = all_maxs[v_axis] - all_mins[v_axis]
        view = View(label=label, width=width, height=height)
        result[label] = {"view": view, "rects": rects, "hardware": hardware_polys, "origin": (u0, v0)}

    return result