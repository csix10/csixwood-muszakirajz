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