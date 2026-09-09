"""
Befoglaló-doboz (bounding box) segédfüggvények.
"""
from __future__ import annotations
import numpy as np
from skp2draw.parser.model import Mesh, Node


def local_bbox(mesh: Mesh):
    """A mesh saját (HELYI, nem világ-) koordinátás min/max sarokpontjai, mm-ben."""
    mins = mesh.vertices_mm.min(axis=0)
    maxs = mesh.vertices_mm.max(axis=0)
    return mins, maxs


def world_bbox(node: Node):
    """A node geometriájának VILÁG-koordinátás befoglaló doboza, mm-ben."""
    if node.mesh is None or len(node.mesh.vertices_mm) == 0:
        return None
    pts_local = node.mesh.vertices_mm
    ones = np.ones((pts_local.shape[0], 1))
    pts_h = np.hstack([pts_local, ones])
    pts_world = (node.world_matrix @ pts_h.T).T[:, :3]
    return pts_world.min(axis=0), pts_world.max(axis=0)


def scaled_local_sizes(node: Node):
    """
    A node geometriájának valós, beépített mérete a SAJÁT (helyi) tengelyei
    mentén, mm-ben: a helyi bbox mérete megszorozva a világmátrix skálázó
    részével (a 3x3 blokk oszlopainak hossza).

    Ez azért kell, mert néhány komponens egy közös "mester" alakzatot használ,
    amit a világmátrix NEM egyenletesen skáláz a tényleges méretre (pl. egy
    sablon-panelt minden konkrét nyílásméretre nyújtanak/zsugorítanak).

    FONTOS: ez a módszer FÜGGETLEN attól, hogy a komponens hogyan van
    elforgatva a világban (tetszőleges szögben is helyesen működik),
    szemben azzal, ha egyszerűen a világkoordinátás AABB-t vennénk (ami
    csak 90 fokos többszöröseinél adná vissza a valódi méretet).
    """
    if node.mesh is None or len(node.mesh.vertices_mm) == 0:
        return None
    mins, maxs = local_bbox(node.mesh)
    local_sizes = maxs - mins
    col_scales = np.linalg.norm(node.world_matrix[0:3, 0:3], axis=0)
    return local_sizes * col_scales

def subtree_bbox_in_frame(node: Node, frame: np.ndarray):
    """
    A node részfája (önmaga + minden leszármazottja) összes geometriájának
    befoglaló doboza egy adott keretben (frame) kifejezve: minden pontot a
    frame INVERZ mátrixával transzformálunk, mielőtt a min/max-ot számoljuk.

    Ha frame = a node SAJÁT world_matrix-a, az eredmény a node saját
    (elöl-nézeti) tengelyei mentén adja a teljes összeállítás méretét -
    FÜGGETLENÜL attól, hogy a node hogyan van elforgatva/elhelyezve a
    világban (pl. egy sarokelem, ami más fal felé néz, mint a többi modul).

    Ha frame = np.eye(4), a VILÁG-keretben számolja a befoglaló dobozt
    (ez kell a teljes elrendezés-rajzhoz, ahol a modulok egymáshoz képesti
    tényleges világpozíciója számít).
    """
    inv_frame = np.linalg.inv(frame)
    points = []

    def walk(n: Node):
        if n.has_geometry:
            pts_local = n.mesh.vertices_mm
            ones = np.ones((pts_local.shape[0], 1))
            pts_h = np.hstack([pts_local, ones])
            pts_world = (n.world_matrix @ pts_h.T).T
            pts_frame = (inv_frame @ pts_world.T).T[:, :3]
            points.append(pts_frame)
        for c in n.children:
            walk(c)

    walk(node)
    if not points:
        return None
    all_pts = np.vstack(points)
    return all_pts.min(axis=0), all_pts.max(axis=0)


def subtree_world_bbox(node: Node):
    """A node részfájának befoglaló doboza a VILÁG-keretben (lásd fent)."""
    return subtree_bbox_in_frame(node, np.eye(4))

def subtree_points_in_frame(node: Node, frame: np.ndarray):
    """
    A node részfájának ÖSSZES geometria-pontja, egy adott keretben (frame)
    kifejezve - ez kell a nem-téglalap alakú hardware-elemek (lábak,
    pántok stb.) körvonalának (konvex burok) kiszámításához.
    """
    inv_frame = np.linalg.inv(frame)
    points = []

    def walk(n: Node):
        if n.has_geometry:
            pts_local = n.mesh.vertices_mm
            ones = np.ones((pts_local.shape[0], 1))
            pts_h = np.hstack([pts_local, ones])
            pts_world = (n.world_matrix @ pts_h.T).T
            pts_frame = (inv_frame @ pts_world.T).T[:, :3]
            points.append(pts_frame)
        for c in n.children:
            walk(c)

    walk(node)
    if not points:
        return None
    return np.vstack(points)